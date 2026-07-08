"""
JULIUS — Metrics Collector
==========================
Continuously polls every active mix-node's /mix/status endpoint, stores
snapshots in a local SQLite database with a configurable retention window,
and exposes query helpers consumed by the Guardian API.

Key design decisions
--------------------
* Pure asyncio – ``collect_all_nodes`` uses ``asyncio.gather`` so all nodes
  are polled concurrently; slow/unreachable nodes are isolated (timeout).
* SQLite-backed storage – self-contained, no external service dependency.
  Old rows are pruned periodically; a WAL journal is used for concurrency.
* Health thresholds are read from ``config.py`` so operators can override
  them via environment variables without code changes.
* Node list is sourced from the partner onboarding registry (active partners)
  and supplemented with any statically configured nodes in the env.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers (lazy — avoids import-time side-effects)
# ---------------------------------------------------------------------------


def _cfg_interval() -> int:
    from ..config import VEIL_COLLECTOR_INTERVAL  # type: ignore
    return VEIL_COLLECTOR_INTERVAL


def _cfg_retention_days() -> int:
    from ..config import VEIL_COLLECTOR_HISTORY_RETENTION_DAYS  # type: ignore
    return VEIL_COLLECTOR_HISTORY_RETENTION_DAYS


def _cfg_alert_latency() -> float:
    from ..config import VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY  # type: ignore
    return VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY


def _cfg_alert_queue() -> int:
    from ..config import VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE  # type: ignore
    return VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE


def _cfg_db_dir() -> str:
    from ..config import DB_DIR  # type: ignore
    return DB_DIR


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """
    Periodically collects performance and health metrics from all active
    mix-nodes and stores them in a local SQLite database.

    Usage (inside FastAPI lifespan)
    --------------------------------
    ::

        collector = MetricsCollector()
        task = asyncio.create_task(collector.run_forever())
        ...
        task.cancel()
    """

    _DB_FILENAME = "metrics.db"
    _HTTP_TIMEOUT = 5  # seconds per node request

    def __init__(self, db_path: Optional[str] = None) -> None:
        db_dir = _cfg_db_dir()
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(db_dir, self._DB_FILENAME)
        self._init_db()
        self.collector_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]
        logger.info("MetricsCollector initialised — db=%s", self.db_path)

    # ------------------------------------------------------------------
    # Database initialisation
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        """Yield a WAL-mode SQLite connection, auto-commit / rollback."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create the metrics table and indices if they do not exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS node_metrics (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id         TEXT    NOT NULL,
                    timestamp       TEXT    NOT NULL,
                    json_data       TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_nm_node_ts
                    ON node_metrics (node_id, timestamp DESC);

                CREATE INDEX IF NOT EXISTS idx_nm_ts
                    ON node_metrics (timestamp DESC);

                CREATE TABLE IF NOT EXISTS network_metrics (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    json_data       TEXT    NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_netm_ts
                    ON network_metrics (timestamp DESC);
                """
            )

    # ------------------------------------------------------------------
    # Node registry
    # ------------------------------------------------------------------

    def _get_active_nodes(self) -> Dict[str, str]:
        """
        Return a mapping of {node_id: base_url} for all nodes to poll.

        Sources (in priority order):
        1. Active partners in the onboarding database (have a ``node_url``).
        2. Discovered nodes that expose an HTTP status endpoint (best-effort).
        3. Env var ``VEIL_EXTRA_NODE_URLS`` (comma-separated, format id=url).
        """
        nodes: Dict[str, str] = {}

        # 1 — Partner onboarding registry
        try:
            from ..guardian.onboarding import onboarding_service  # type: ignore

            partners = onboarding_service.list_partners(filters={"status": "active"})
            for p in partners:
                pid = p.get("partner_id") or p.get("node_id")
                url = p.get("node_url") or p.get("host_url")
                if pid and url:
                    nodes[pid] = url.rstrip("/")
        except Exception as exc:
            logger.debug("Onboarding registry not available: %s", exc)

        # 2 — Extra nodes from env (useful for tests / manual config)
        extra = os.getenv("VEIL_EXTRA_NODE_URLS", "")
        for item in extra.split(","):
            item = item.strip()
            if "=" in item:
                nid, nurl = item.split("=", 1)
                nodes[nid.strip()] = nurl.strip().rstrip("/")

        return nodes

    # ------------------------------------------------------------------
    # HTTP helper (sync — runs in executor)
    # ------------------------------------------------------------------

    @staticmethod
    def _http_get_status(base_url: str, timeout: int = 5) -> Optional[dict]:
        """
        Perform a synchronous GET to ``{base_url}/mix/status``.
        Returns the parsed JSON dict or None on any error.
        """
        url = f"{base_url}/mix/status"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "JULIUS-Collector/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except Exception as exc:
            logger.debug("HTTP GET %s failed: %s", url, exc)
            return None

    # ------------------------------------------------------------------
    # Single-node collection
    # ------------------------------------------------------------------

    async def collect_from_node(self, node_id: str, base_url: str) -> Optional["NodeMetric"]:
        """
        Fetch ``/mix/status`` from one node, store the result, and return a
        ``NodeMetric``.  Returns ``None`` when the node is unreachable.
        """
        from ..models.metric_models import NodeMetric  # type: ignore

        loop = asyncio.get_event_loop()
        try:
            raw = await asyncio.wait_for(
                loop.run_in_executor(None, self._http_get_status, base_url, self._HTTP_TIMEOUT),
                timeout=self._HTTP_TIMEOUT + 1,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            logger.debug("collect_from_node %s: timeout/error — %s", node_id, exc)
            return None

        if raw is None:
            return None

        # Normalise timestamp
        ts = datetime.now(tz=timezone.utc)

        try:
            metric = NodeMetric(
                node_id=raw.get("node_id", node_id),
                timestamp=ts,
                uptime_seconds=float(raw.get("uptime_seconds", 0.0)),
                queue_size=int(raw.get("queue_size", 0)),
                packets_processed=int(raw.get("packets_processed", 0)),
                packets_forwarded=int(raw.get("packets_forwarded", 0)),
                bytes_processed=int(raw.get("bytes_processed", 0)),
                latency_avg_ms=float(raw.get("latency_avg_ms", 0.0)),
                latency_p95_ms=float(raw.get("latency_p95_ms", 0.0)),
                cpu_percent=float(raw.get("cpu_percent", 0.0)),
                memory_usage_mb=float(raw.get("memory_usage_mb", 0.0)),
                active_connections=int(raw.get("active_connections", 0)),
                cover_traffic_rate=float(raw.get("cover_traffic_rate", 0.0)),
                mixing_delay_current=float(raw.get("mixing_delay_current", 0.0)),
                strata_count=int(raw.get("strata_count", 0)),
            )
        except Exception as exc:
            logger.warning("collect_from_node %s: failed to parse response — %s", node_id, exc)
            return None

        self._store_metric(metric)
        return metric

    def _store_metric(self, metric: "NodeMetric") -> None:
        """Persist a NodeMetric snapshot to SQLite."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO node_metrics (node_id, timestamp, json_data) VALUES (?, ?, ?)",
                (
                    metric.node_id,
                    metric.timestamp.isoformat(),
                    metric.model_dump_json(),
                ),
            )

    # ------------------------------------------------------------------
    # Network-wide collection
    # ------------------------------------------------------------------

    async def collect_all_nodes(self) -> "NetworkMetrics":
        """
        Poll all active nodes concurrently and build a ``NetworkMetrics``
        aggregate.  Unreachable nodes are counted against ``total_nodes``
        but not ``active_nodes``.
        """
        from ..models.metric_models import NetworkMetrics  # type: ignore

        nodes = self._get_active_nodes()
        total = len(nodes)
        ts = datetime.now(tz=timezone.utc)

        if not nodes:
            logger.debug("collect_all_nodes: no active nodes in registry")
            net = NetworkMetrics(
                timestamp=ts,
                total_nodes=0,
                active_nodes=0,
                total_bandwidth_bps=0.0,
                average_latency_ms=0.0,
                total_queue_size=0,
                total_packets_processed=0,
                health_breakdown={"healthy": 0, "warning": 0, "critical": 0},
            )
            self._store_network_metric(net)
            return net

        tasks = [
            self.collect_from_node(nid, url) for nid, url in nodes.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        metrics = []
        for nid, result in zip(nodes.keys(), results):
            if isinstance(result, Exception):
                logger.warning("Node %s raised exception during collect: %s", nid, result)
            elif result is not None:
                metrics.append(result)

        active = len(metrics)
        health_breakdown: Dict[str, int] = {"healthy": 0, "warning": 0, "critical": 0}
        total_latency = 0.0
        total_queue = 0
        total_packets = 0
        total_bps = 0.0

        for m in metrics:
            status = self.get_health_status(m)
            health_breakdown[status] = health_breakdown.get(status, 0) + 1
            total_latency += m.latency_avg_ms
            total_queue += m.queue_size
            total_packets += m.packets_processed
            # Rough bps estimate: bytes_processed since startup is monotonic,
            # so we use queue_size * avg_latency as a proxy for current load.
            if m.uptime_seconds > 0:
                total_bps += m.bytes_processed / m.uptime_seconds

        avg_latency = total_latency / active if active else 0.0

        net = NetworkMetrics(
            timestamp=ts,
            total_nodes=total,
            active_nodes=active,
            total_bandwidth_bps=round(total_bps, 2),
            average_latency_ms=round(avg_latency, 3),
            total_queue_size=total_queue,
            total_packets_processed=total_packets,
            health_breakdown=health_breakdown,
        )
        self._store_network_metric(net)

        logger.info(
            "collect_all_nodes: total=%d active=%d healthy=%d warning=%d critical=%d",
            total,
            active,
            health_breakdown.get("healthy", 0),
            health_breakdown.get("warning", 0),
            health_breakdown.get("critical", 0),
        )
        return net

    def _store_network_metric(self, net: "NetworkMetrics") -> None:
        """Persist a NetworkMetrics snapshot to SQLite."""
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO network_metrics (timestamp, json_data) VALUES (?, ?)",
                (net.timestamp.isoformat(), net.model_dump_json()),
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_node_metrics(self, node_id: str, hours: int = 24) -> List["NodeMetric"]:
        """Return historical metrics for ``node_id`` over the last ``hours``."""
        from ..models.metric_models import NodeMetric  # type: ignore

        cutoff = (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT json_data FROM node_metrics
                WHERE node_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                """,
                (node_id, cutoff),
            ).fetchall()

        result = []
        for row in rows:
            try:
                result.append(NodeMetric.model_validate_json(row["json_data"]))
            except Exception as exc:
                logger.debug("Failed to parse stored metric row: %s", exc)
        return result

    def get_node_latest(self, node_id: str) -> Optional["NodeMetric"]:
        """Return the most recent metric snapshot for ``node_id``."""
        from ..models.metric_models import NodeMetric  # type: ignore

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT json_data FROM node_metrics
                WHERE node_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (node_id,),
            ).fetchone()

        if row is None:
            return None
        try:
            return NodeMetric.model_validate_json(row["json_data"])
        except Exception as exc:
            logger.debug("Failed to parse latest metric: %s", exc)
            return None

    def get_all_node_ids(self) -> List[str]:
        """Return all node IDs that have at least one stored metric."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT node_id FROM node_metrics ORDER BY node_id"
            ).fetchall()
        return [r["node_id"] for r in rows]

    def get_network_summary(self) -> Optional["NetworkMetrics"]:
        """Return the most recent network-wide aggregate snapshot."""
        from ..models.metric_models import NetworkMetrics  # type: ignore

        with self._conn() as conn:
            row = conn.execute(
                "SELECT json_data FROM network_metrics ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()

        if row is None:
            return None
        try:
            return NetworkMetrics.model_validate_json(row["json_data"])
        except Exception as exc:
            logger.debug("Failed to parse network summary: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Health determination
    # ------------------------------------------------------------------

    def get_health_status(self, metric: "NodeMetric") -> str:
        """
        Classify a node metric snapshot into one of three health buckets:

        * **critical** — latency above ``VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY``
          (expressed in seconds; the metric stores ms so we convert).
        * **warning**  — queue depth above ``VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE``
          OR uptime < 60 s (node just restarted).
        * **healthy**  — everything within normal bounds.
        """
        latency_threshold_ms = _cfg_alert_latency() * 1_000  # s → ms
        queue_threshold = _cfg_alert_queue()

        if metric.latency_avg_ms > latency_threshold_ms:
            return "critical"

        if metric.queue_size > queue_threshold:
            return "warning"

        # Treat very low uptime (< 60 s) as a warning — node may still be
        # stabilising and could be in an unreliable transient state.
        if metric.uptime_seconds < 60:
            return "warning"

        return "healthy"

    # ------------------------------------------------------------------
    # Data pruning
    # ------------------------------------------------------------------

    def prune_old_data(self) -> None:
        """Delete metric rows older than the configured retention period."""
        retention_days = _cfg_retention_days()
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
        ).isoformat()

        with self._conn() as conn:
            deleted_nm = conn.execute(
                "DELETE FROM node_metrics WHERE timestamp < ?", (cutoff,)
            ).rowcount
            deleted_net = conn.execute(
                "DELETE FROM network_metrics WHERE timestamp < ?", (cutoff,)
            ).rowcount

        logger.info(
            "prune_old_data: removed %d node-metric rows and %d network-metric rows "
            "older than %d days",
            deleted_nm,
            deleted_net,
            retention_days,
        )

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """
        Background coroutine: collect metrics every ``VEIL_COLLECTOR_INTERVAL``
        seconds.  Prunes old data once per cycle as well.
        Should be wrapped in ``asyncio.create_task()``.
        """
        interval = _cfg_interval()
        logger.info("Metrics collector loop started (interval=%ds)", interval)
        # Small initial delay so the rest of the app is fully ready.
        await asyncio.sleep(15)

        while True:
            try:
                net = await self.collect_all_nodes()
                logger.info(
                    "Metrics cycle complete | active=%d/%d "
                    "healthy=%d warning=%d critical=%d avg_latency=%.1fms",
                    net.active_nodes,
                    net.total_nodes,
                    net.health_breakdown.get("healthy", 0),
                    net.health_breakdown.get("warning", 0),
                    net.health_breakdown.get("critical", 0),
                    net.average_latency_ms,
                )
            except Exception as exc:
                logger.warning("Metrics collect cycle failed: %s", exc)

            # Prune old data (best-effort, non-blocking)
            try:
                self.prune_old_data()
            except Exception as exc:
                logger.debug("Metrics prune failed: %s", exc)

            await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

metrics_collector = MetricsCollector()
