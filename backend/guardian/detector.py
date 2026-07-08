"""
JULIUS — Attack Detector
========================
The "immune system" of the Guardian network.

Monitors the mix-node network for four classes of attack:

1. **Timing attacks** — unusual latency deviations that may indicate traffic
   correlation by an adversary observing both ends of a circuit.
2. **Sybil attacks** — many nodes sharing an identical fingerprint (software
   version, IP prefix, or configuration), suggesting a single actor
   running many pseudo-independent nodes.
3. **Intersection attacks** — repeated connection patterns to the same
   hidden service that, over time, narrow the anonymity set of users.
4. **Node compromise** — dramatic behavioural deviations from a node's
   historical baseline (latency, queue size, CPU), suggesting the node has
   been tampered with or taken over.

When an attack is detected an ``AttackAlert`` is created, stored in
``detector.db`` (SQLite), and handled according to its severity:

* ``low``      — logged only.
* ``medium``   — automatic defence action executed.
* ``high``     — auto-respond **and** escalate to human operator.
* ``critical`` — blacklist, escalate, rotate all circuits.

Design decisions
----------------
* All detection helpers are ``async`` so they can be awaited inside the
  background loop and called from the FastAPI thread.
* SQLite is used (WAL mode) — same pattern as the MetricsCollector.
* KnowledgeGraph interaction is lightweight (query-only).
* All defence actions are best-effort; failures are logged but do not
  prevent the detection loop from continuing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers (lazy)
# ---------------------------------------------------------------------------


def _cfg_enabled() -> bool:
    from ..config import VEIL_DETECTOR_ENABLED  # type: ignore
    return VEIL_DETECTOR_ENABLED


def _cfg_interval() -> int:
    from ..config import VEIL_DETECTOR_INTERVAL  # type: ignore
    return VEIL_DETECTOR_INTERVAL


def _cfg_timing_threshold() -> float:
    from ..config import VEIL_DETECTOR_TIMING_THRESHOLD  # type: ignore
    return VEIL_DETECTOR_TIMING_THRESHOLD


def _cfg_sybil_threshold() -> int:
    from ..config import VEIL_DETECTOR_SYBIL_THRESHOLD  # type: ignore
    return VEIL_DETECTOR_SYBIL_THRESHOLD


def _cfg_intersection_threshold() -> int:
    from ..config import VEIL_DETECTOR_INTERSECTION_THRESHOLD  # type: ignore
    return VEIL_DETECTOR_INTERSECTION_THRESHOLD


def _cfg_auto_respond() -> bool:
    from ..config import VEIL_DETECTOR_AUTO_RESPOND  # type: ignore
    return VEIL_DETECTOR_AUTO_RESPOND


def _cfg_db_dir() -> str:
    from ..config import DB_DIR  # type: ignore
    return DB_DIR


# ---------------------------------------------------------------------------
# Lightweight KnowledgeGraph stub (query-only)
# ---------------------------------------------------------------------------


class KnowledgeGraph:
    """
    Lightweight wrapper around the discovery engine's SQLite database.
    Used read-only by the detector to query node fingerprints and
    connection patterns without coupling to the full DiscoveryEngine.
    """

    def __init__(self) -> None:
        self._db_path: Optional[str] = None

    def _get_db_path(self) -> Optional[str]:
        if self._db_path:
            return self._db_path
        try:
            from ..guardian.discovery import discovery_engine  # type: ignore
            self._db_path = discovery_engine.db_path
        except Exception:
            try:
                db_dir = _cfg_db_dir()
                candidate = os.path.join(db_dir, "discovery.db")
                if os.path.exists(candidate):
                    self._db_path = candidate
            except Exception:
                pass
        return self._db_path

    def get_all_nodes(self) -> List[Dict]:
        """Return all nodes stored in the knowledge graph."""
        path = self._get_db_path()
        if not path:
            return []
        try:
            conn = sqlite3.connect(path, timeout=5)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT node_id, network, version, ip_address "
                "FROM discovered_nodes"
            ).fetchall()
            conn.close()
            result = []
            for row in rows:
                raw = {
                    "node_id": row["node_id"],
                    "network": row["network"],
                    "software_version": row["version"],
                    "ip_address": row["ip_address"],
                }
                result.append(raw)
            return result
        except Exception as exc:
            logger.debug("KnowledgeGraph.get_all_nodes failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# AttackDetector
# ---------------------------------------------------------------------------


class AttackDetector:
    """
    The immune system of the Guardian network.

    Usage (inside FastAPI lifespan)::

        detector = AttackDetector()
        task = asyncio.create_task(detector.run_forever())
    """

    _DB_FILENAME = "detector.db"

    def __init__(self, db_path: Optional[str] = None) -> None:
        from ..guardian.collector import metrics_collector  # type: ignore
        from ..guardian.optimizer import network_optimizer  # type: ignore

        self.collector = metrics_collector
        self.optimizer = network_optimizer
        self.knowledge_graph = KnowledgeGraph()

        self.alert_history: List["AttackAlert"] = []  # type: ignore[name-defined]
        self.defense_actions: List["DefenseAction"] = []  # type: ignore[name-defined]
        self._detection_cache: Dict = {}

        db_dir = _cfg_db_dir()
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(db_dir, self._DB_FILENAME)
        self._init_db()

        self._running = False
        self._last_run: Optional[datetime] = None

        logger.info("AttackDetector initialised — db=%s", self.db_path)

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        """WAL-mode SQLite connection."""
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
        """Create database tables if they do not exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id    TEXT PRIMARY KEY,
                    alert_type  TEXT NOT NULL,
                    severity    TEXT NOT NULL,
                    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    node_ids    TEXT,
                    description TEXT,
                    evidence    TEXT,
                    confidence  REAL,
                    status      TEXT DEFAULT 'open',
                    auto_response TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_alerts_status
                    ON alerts (status);

                CREATE INDEX IF NOT EXISTS idx_alerts_type
                    ON alerts (alert_type);

                CREATE TABLE IF NOT EXISTS defense_actions (
                    action_id   TEXT PRIMARY KEY,
                    alert_id    TEXT,
                    action_type TEXT NOT NULL,
                    target_node TEXT,
                    status      TEXT DEFAULT 'pending',
                    executed_at TIMESTAMP,
                    result      TEXT,
                    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id)
                );
                """
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_id() -> str:
        return str(uuid.uuid4())

    def _store_alert(self, alert: "AttackAlert") -> None:  # type: ignore[name-defined]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO alerts
                    (alert_id, alert_type, severity, timestamp, node_ids,
                     description, evidence, confidence, status, auto_response)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.alert_type,
                    alert.severity,
                    alert.timestamp.isoformat(),
                    json.dumps(alert.node_ids),
                    alert.description,
                    json.dumps(alert.evidence),
                    alert.confidence,
                    alert.status,
                    alert.auto_response,
                ),
            )

    def _store_action(self, action: "DefenseAction") -> None:  # type: ignore[name-defined]
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO defense_actions
                    (action_id, alert_id, action_type, target_node,
                     status, executed_at, result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id,
                    action.alert_id,
                    action.action_type,
                    action.target_node,
                    action.status,
                    action.executed_at.isoformat() if action.executed_at else None,
                    action.result,
                ),
            )

    # ------------------------------------------------------------------
    # Main detection entry-point
    # ------------------------------------------------------------------

    async def detect_attacks(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """
        Run all four detection algorithms and handle any alerts found.
        Returns the list of new alerts generated in this cycle.
        """
        from ..models.alert_models import AttackAlert  # type: ignore

        alerts: List[AttackAlert] = []

        # 1 — Timing attacks
        try:
            timing_alerts = await self._detect_timing_attacks()
            alerts.extend(timing_alerts)
        except Exception as exc:
            logger.warning("Timing attack detection failed: %s", exc)

        # 2 — Sybil attacks
        try:
            sybil_alerts = await self._detect_sybil_attacks()
            alerts.extend(sybil_alerts)
        except Exception as exc:
            logger.warning("Sybil attack detection failed: %s", exc)

        # 3 — Intersection attacks
        try:
            intersection_alerts = await self._detect_intersection_attacks()
            alerts.extend(intersection_alerts)
        except Exception as exc:
            logger.warning("Intersection attack detection failed: %s", exc)

        # 4 — Node compromise
        try:
            compromise_alerts = await self._detect_node_compromise()
            alerts.extend(compromise_alerts)
        except Exception as exc:
            logger.warning("Node compromise detection failed: %s", exc)

        # Handle and persist each new alert
        for alert in alerts:
            try:
                await self._handle_alert(alert)
            except Exception as exc:
                logger.warning("Handle alert %s failed: %s", alert.alert_id, exc)

        self._last_run = datetime.now(tz=timezone.utc)

        if alerts:
            logger.info(
                "detect_attacks: %d new alert(s) | timing=%d sybil=%d "
                "intersection=%d compromise=%d",
                len(alerts),
                sum(1 for a in alerts if a.alert_type == "timing_attack"),
                sum(1 for a in alerts if a.alert_type == "sybil_attack"),
                sum(1 for a in alerts if a.alert_type == "intersection_attack"),
                sum(1 for a in alerts if a.alert_type == "node_compromise"),
            )
        else:
            logger.debug("detect_attacks: no new alerts this cycle")

        return alerts

    # ------------------------------------------------------------------
    # Detection algorithms
    # ------------------------------------------------------------------

    async def _detect_timing_attacks(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """
        Timing correlation attack detection.

        For each node, compare the most recent latency against the rolling
        mean of its historical latencies.  If the deviation exceeds
        ``VEIL_DETECTOR_TIMING_THRESHOLD`` standard deviations, generate a
        timing-attack alert.
        """
        from ..models.alert_models import AttackAlert  # type: ignore

        alerts: List[AttackAlert] = []
        threshold = _cfg_timing_threshold()
        node_ids = self.collector.get_all_node_ids()

        for node_id in node_ids:
            try:
                # Fetch recent history (last 24 h)
                history = self.collector.get_node_metrics(node_id, hours=24)
                if len(history) < 3:
                    continue  # insufficient data for baseline

                latencies = [m.latency_avg_ms for m in history]
                # Exclude the most recent point from the baseline
                baseline = latencies[1:]
                current = latencies[0]

                mean = sum(baseline) / len(baseline)
                variance = sum((x - mean) ** 2 for x in baseline) / len(baseline)
                std_dev = math.sqrt(variance) if variance > 0 else 0.0

                if std_dev < 1.0:
                    continue  # stable node, nothing to flag

                z_score = abs(current - mean) / std_dev

                if z_score > threshold:
                    confidence = min(1.0, (z_score - threshold) / threshold)
                    alert = AttackAlert(
                        alert_id=self._generate_id(),
                        alert_type="timing_attack",
                        severity=self._latency_severity(z_score, threshold),
                        timestamp=datetime.now(tz=timezone.utc),
                        node_ids=[node_id],
                        description=(
                            f"Node {node_id} latency deviation {z_score:.2f}σ "
                            f"exceeds threshold {threshold}σ. "
                            f"Current: {current:.1f}ms, Mean: {mean:.1f}ms"
                        ),
                        evidence={
                            "node_id": node_id,
                            "current_latency_ms": current,
                            "baseline_mean_ms": round(mean, 2),
                            "baseline_std_dev": round(std_dev, 2),
                            "z_score": round(z_score, 3),
                            "threshold": threshold,
                        },
                        confidence=round(confidence, 3),
                    )
                    alerts.append(alert)
                    self.alert_history.append(alert)
            except Exception as exc:
                logger.debug("Timing check for node %s failed: %s", node_id, exc)

        return alerts

    @staticmethod
    def _latency_severity(z_score: float, threshold: float) -> str:
        ratio = z_score / threshold
        if ratio >= 5:
            return "critical"
        if ratio >= 3:
            return "high"
        if ratio >= 1.5:
            return "medium"
        return "low"

    async def _detect_sybil_attacks(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """
        Sybil attack detection.

        Group all nodes by a fingerprint derived from their software version
        and IP prefix (/24).  If any group exceeds ``VEIL_DETECTOR_SYBIL_THRESHOLD``
        nodes, flag as a potential Sybil cluster.
        """
        from ..models.alert_models import AttackAlert  # type: ignore

        alerts: List[AttackAlert] = []
        threshold = _cfg_sybil_threshold()

        nodes = self.knowledge_graph.get_all_nodes()
        if not nodes:
            # Fall back to onboarding registry
            try:
                from ..guardian.onboarding import onboarding_service  # type: ignore
                partners = onboarding_service.list_partners(filters={"status": "active"})
                nodes = [
                    {
                        "node_id": p.get("partner_id", ""),
                        "software_version": p.get("node_metadata", {}).get("version", "unknown"),
                        "ip_address": p.get("ip_address", ""),
                    }
                    for p in partners
                ]
            except Exception:
                return alerts

        # Build fingerprint → list-of-nodes map
        fingerprint_map: Dict[str, List[str]] = defaultdict(list)
        for node in nodes:
            nid = node.get("node_id", "")
            if not nid:
                continue
            version = str(node.get("software_version") or "unknown")
            ip = str(node.get("ip_address") or "")
            # Derive /24 prefix
            ip_prefix = ".".join(ip.split(".")[:3]) if ip else "unknown"
            fingerprint = f"{version}|{ip_prefix}"
            fingerprint_map[fingerprint].append(nid)

        for fingerprint, node_ids in fingerprint_map.items():
            if len(node_ids) >= threshold:
                confidence = min(1.0, (len(node_ids) - threshold) / threshold + 0.5)
                severity = "critical" if len(node_ids) >= threshold * 3 else (
                    "high" if len(node_ids) >= threshold * 2 else "medium"
                )
                alert = AttackAlert(
                    alert_id=self._generate_id(),
                    alert_type="sybil_attack",
                    severity=severity,
                    timestamp=datetime.now(tz=timezone.utc),
                    node_ids=node_ids,
                    description=(
                        f"Sybil cluster detected: {len(node_ids)} nodes share "
                        f"fingerprint '{fingerprint}' (threshold: {threshold})"
                    ),
                    evidence={
                        "fingerprint": fingerprint,
                        "node_count": len(node_ids),
                        "node_ids": node_ids,
                        "threshold": threshold,
                    },
                    confidence=round(confidence, 3),
                )
                alerts.append(alert)
                self.alert_history.append(alert)

        return alerts

    async def _detect_intersection_attacks(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """
        Intersection attack detection.

        Track repeated connections to the same target (hidden service / node)
        across multiple nodes.  If a single target appears in more than
        ``VEIL_DETECTOR_INTERSECTION_THRESHOLD`` distinct node connection
        windows, flag an intersection attack.

        In the MVP we proxy this by checking how many nodes have been
        observed exchanging traffic with each other (via queue-size
        co-variance patterns).  Real deployments would plug in actual
        connection logs.
        """
        from ..models.alert_models import AttackAlert  # type: ignore

        alerts: List[AttackAlert] = []
        threshold = _cfg_intersection_threshold()

        # Use detection cache to track connection counts between cycles
        # Key: service_id, Value: count of observations
        if "connection_counts" not in self._detection_cache:
            self._detection_cache["connection_counts"] = defaultdict(int)

        node_ids = self.collector.get_all_node_ids()
        for node_id in node_ids:
            latest = self.collector.get_node_latest(node_id)
            if latest is None:
                continue
            # Active connections act as a proxy for connection targets
            if latest.active_connections > 0:
                # In a real system we'd have per-target connection logs.
                # Here we accumulate per-node connection events as a proxy.
                self._detection_cache["connection_counts"][node_id] += latest.active_connections

        flagged: Dict[str, int] = {
            sid: cnt
            for sid, cnt in self._detection_cache["connection_counts"].items()
            if cnt >= threshold
        }

        for target, count in flagged.items():
            confidence = min(1.0, (count - threshold) / (threshold * 2) + 0.4)
            severity = "high" if count >= threshold * 3 else "medium"
            alert = AttackAlert(
                alert_id=self._generate_id(),
                alert_type="intersection_attack",
                severity=severity,
                timestamp=datetime.now(tz=timezone.utc),
                node_ids=[target],
                description=(
                    f"Intersection attack suspected: node '{target}' has accumulated "
                    f"{count} connection observations (threshold: {threshold})"
                ),
                evidence={
                    "target_node": target,
                    "observation_count": count,
                    "threshold": threshold,
                },
                confidence=round(confidence, 3),
            )
            alerts.append(alert)
            self.alert_history.append(alert)
            # Reset count after alerting to avoid re-alerting every cycle
            self._detection_cache["connection_counts"][target] = 0

        return alerts

    async def _detect_node_compromise(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """
        Node compromise / behavioural anomaly detection.

        Compare each node's current CPU usage and queue size against its
        rolling 24-hour baseline.  Nodes that deviate dramatically (3×
        baseline) are flagged as potentially compromised.
        """
        from ..models.alert_models import AttackAlert  # type: ignore

        alerts: List[AttackAlert] = []
        node_ids = self.collector.get_all_node_ids()

        for node_id in node_ids:
            try:
                history = self.collector.get_node_metrics(node_id, hours=24)
                if len(history) < 5:
                    continue

                current = history[0]
                baseline = history[1:]

                # Baseline metrics
                avg_cpu = sum(m.cpu_percent for m in baseline) / len(baseline)
                avg_queue = sum(m.queue_size for m in baseline) / len(baseline)

                anomaly_flags = []
                evidence: Dict = {
                    "node_id": node_id,
                    "current_cpu": current.cpu_percent,
                    "baseline_cpu": round(avg_cpu, 2),
                    "current_queue": current.queue_size,
                    "baseline_queue": round(avg_queue, 2),
                }

                # CPU spike: current > 3× baseline (minimum 20% CPU)
                if avg_cpu > 0 and current.cpu_percent > max(avg_cpu * 3, 20):
                    anomaly_flags.append(
                        f"CPU spike: {current.cpu_percent:.1f}% vs baseline {avg_cpu:.1f}%"
                    )
                    evidence["cpu_ratio"] = round(current.cpu_percent / avg_cpu, 2)

                # Queue explosion: current > 5× baseline (minimum 20 packets)
                if avg_queue > 0 and current.queue_size > max(avg_queue * 5, 20):
                    anomaly_flags.append(
                        f"Queue explosion: {current.queue_size} vs baseline {avg_queue:.0f}"
                    )
                    evidence["queue_ratio"] = round(current.queue_size / (avg_queue + 1), 2)

                if not anomaly_flags:
                    continue

                confidence = min(1.0, len(anomaly_flags) * 0.4 + 0.2)
                severity = "critical" if len(anomaly_flags) >= 2 else "high"
                alert = AttackAlert(
                    alert_id=self._generate_id(),
                    alert_type="node_compromise",
                    severity=severity,
                    timestamp=datetime.now(tz=timezone.utc),
                    node_ids=[node_id],
                    description=(
                        f"Node {node_id} shows behavioural anomalies: "
                        + "; ".join(anomaly_flags)
                    ),
                    evidence=evidence,
                    confidence=round(confidence, 3),
                )
                alerts.append(alert)
                self.alert_history.append(alert)
            except Exception as exc:
                logger.debug("Compromise check for node %s failed: %s", node_id, exc)

        return alerts

    # ------------------------------------------------------------------
    # Alert handling & defence
    # ------------------------------------------------------------------

    async def _handle_alert(self, alert: "AttackAlert") -> Optional["DefenseAction"]:  # type: ignore[name-defined]
        """Persist an alert and trigger the appropriate defence action."""
        # Persist to DB
        self._store_alert(alert)

        if not _cfg_auto_respond():
            logger.info("Auto-respond disabled — alert %s logged only", alert.alert_id)
            return None

        action: Optional["DefenseAction"] = None  # type: ignore[name-defined]

        if alert.severity == "low":
            # Log only — no automated action
            logger.info("LOW alert %s [%s] — logged only", alert.alert_id, alert.alert_type)

        elif alert.severity == "medium":
            action = await self._auto_respond(alert)

        elif alert.severity == "high":
            await self._escalate(alert)
            action = await self._auto_respond(alert)

        elif alert.severity == "critical":
            action = await self._critical_respond(alert)

        # Log to Pantheon
        self._log_to_pantheon(alert, action)

        return action

    async def _auto_respond(self, alert: "AttackAlert") -> Optional["DefenseAction"]:  # type: ignore[name-defined]
        """Execute an automatic defence action based on alert type."""
        if alert.alert_type == "timing_attack":
            return await self._increase_mixing(alert)
        elif alert.alert_type == "sybil_attack":
            return await self._blacklist_nodes(alert)
        elif alert.alert_type == "intersection_attack":
            return await self._rotate_circuits(alert)
        elif alert.alert_type == "node_compromise":
            if alert.node_ids:
                return await self._isolate_node(alert)
        return None

    async def _critical_respond(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """Critical severity: blacklist, escalate, and rotate everything."""
        from ..models.alert_models import DefenseAction  # type: ignore

        # Escalate
        await self._escalate(alert)
        # Blacklist / isolate all affected nodes
        await self._blacklist_nodes(alert)
        # Rotate circuits
        await self._rotate_circuits(alert)

        # Return a summary action
        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="blacklist_node",
            target_node=alert.node_ids[0] if alert.node_ids else None,
            status="executed",
            executed_at=datetime.now(tz=timezone.utc),
            result=f"Critical response: blacklisted {len(alert.node_ids)} node(s), "
                   "escalated, rotated circuits",
        )
        alert.status = "mitigated"
        alert.auto_response = "blacklist"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        return action

    async def _escalate(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """Create a pending human-escalation action."""
        from ..models.alert_models import DefenseAction  # type: ignore

        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="escalate_human",
            target_node=None,
            status="pending",
            executed_at=datetime.now(tz=timezone.utc),
            result=f"Human review required for {alert.alert_type} alert (severity={alert.severity})",
        )
        alert.auto_response = "escalate"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        logger.warning(
            "ESCALATION REQUIRED | alert_id=%s type=%s severity=%s nodes=%s",
            alert.alert_id,
            alert.alert_type,
            alert.severity,
            alert.node_ids,
        )
        return action

    async def _increase_mixing(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """Increase mixing delay for affected nodes via the optimizer."""
        from ..models.alert_models import DefenseAction  # type: ignore

        results = []
        for node_id in alert.node_ids:
            try:
                ok = await self.optimizer._send_config(node_id, {"lambda": 0.5})
                results.append(f"{node_id}:{'ok' if ok else 'unreachable'}")
            except Exception as exc:
                results.append(f"{node_id}:error({exc})")

        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="increase_mixing",
            target_node=alert.node_ids[0] if alert.node_ids else None,
            status="executed",
            executed_at=datetime.now(tz=timezone.utc),
            result="; ".join(results) if results else "no nodes targeted",
        )
        alert.status = "mitigated"
        alert.auto_response = "rotation"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        return action

    async def _blacklist_nodes(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """
        Blacklist suspicious nodes.
        In the MVP we update the onboarding registry to 'decommissioned'.
        """
        from ..models.alert_models import DefenseAction  # type: ignore

        results = []
        for node_id in alert.node_ids:
            try:
                from ..guardian.onboarding import onboarding_service  # type: ignore
                ok = onboarding_service.decommission_partner(
                    partner_id=node_id,
                    reason=f"Auto-blacklisted due to {alert.alert_type} alert {alert.alert_id}",
                )
                results.append(f"{node_id}:{'blacklisted' if ok else 'not_found'}")
            except Exception as exc:
                results.append(f"{node_id}:error({exc})")

        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="blacklist_node",
            target_node=alert.node_ids[0] if alert.node_ids else None,
            status="executed",
            executed_at=datetime.now(tz=timezone.utc),
            result="; ".join(results) if results else "no nodes targeted",
        )
        alert.status = "mitigated"
        alert.auto_response = "blacklist"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        return action

    async def _rotate_circuits(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """Rotate circuits for affected nodes (advisory — logged and optimizer notified)."""
        from ..models.alert_models import DefenseAction  # type: ignore

        logger.info(
            "CIRCUIT ROTATION advisory for %d node(s): %s",
            len(alert.node_ids),
            alert.node_ids,
        )
        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="rotate_circuits",
            target_node=alert.node_ids[0] if alert.node_ids else None,
            status="executed",
            executed_at=datetime.now(tz=timezone.utc),
            result=f"Circuit rotation advisory issued for {len(alert.node_ids)} node(s)",
        )
        alert.status = "mitigated"
        alert.auto_response = "rotation"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        return action

    async def _isolate_node(self, alert: "AttackAlert") -> "DefenseAction":  # type: ignore[name-defined]
        """Isolate a compromised node by sending it zero-traffic config."""
        from ..models.alert_models import DefenseAction  # type: ignore

        node_id = alert.node_ids[0] if alert.node_ids else ""
        result = "no target"
        if node_id:
            try:
                ok = await self.optimizer._send_config(node_id, {"lambda": 0.001, "cover_ratio": 0.0})
                result = f"isolation config {'sent' if ok else 'failed'}"
            except Exception as exc:
                result = f"error: {exc}"

        action = DefenseAction(
            action_id=self._generate_id(),
            alert_id=alert.alert_id,
            action_type="blacklist_node",
            target_node=node_id or None,
            status="executed",
            executed_at=datetime.now(tz=timezone.utc),
            result=result,
        )
        alert.status = "mitigated"
        alert.auto_response = "blacklist"
        self._store_alert(alert)
        self._store_action(action)
        self.defense_actions.append(action)
        return action

    # ------------------------------------------------------------------
    # Pantheon audit logging
    # ------------------------------------------------------------------

    def _log_to_pantheon(
        self,
        alert: "AttackAlert",  # type: ignore[name-defined]
        action: Optional["DefenseAction"] = None,  # type: ignore[name-defined]
    ) -> None:
        """Log alert + action to the Pantheon audit trail (best-effort)."""
        try:
            from ..services.pantheon.client import pantheon_client  # type: ignore

            pantheon_client.record_event(
                event_type="attack_detector_alert",
                data={
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "timestamp": alert.timestamp.isoformat(),
                    "node_ids": alert.node_ids,
                    "confidence": alert.confidence,
                    "status": alert.status,
                    "action_type": action.action_type if action else None,
                    "action_status": action.status if action else None,
                },
            )
        except Exception as exc:
            logger.debug("Pantheon log skipped: %s", exc)

    # ------------------------------------------------------------------
    # Query helpers (used by Guardian API)
    # ------------------------------------------------------------------

    def get_open_alerts(self) -> List["AttackAlert"]:  # type: ignore[name-defined]
        """Return all currently open (unresolved) alerts from DB."""
        from ..models.alert_models import AttackAlert  # type: ignore

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE status = 'open' ORDER BY timestamp DESC"
            ).fetchall()

        alerts = []
        for row in rows:
            try:
                alerts.append(
                    AttackAlert(
                        alert_id=row["alert_id"],
                        alert_type=row["alert_type"],
                        severity=row["severity"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        node_ids=json.loads(row["node_ids"] or "[]"),
                        description=row["description"] or "",
                        evidence=json.loads(row["evidence"] or "{}"),
                        confidence=row["confidence"] or 0.0,
                        status=row["status"],
                        auto_response=row["auto_response"],
                    )
                )
            except Exception as exc:
                logger.debug("Failed to parse alert row: %s", exc)
        return alerts

    def get_all_alerts(self, status_filter: Optional[str] = None) -> List[Dict]:
        """Return all alerts from DB, optionally filtered by status."""
        with self._conn() as conn:
            if status_filter:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE status = ? ORDER BY timestamp DESC",
                    (status_filter,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts ORDER BY timestamp DESC"
                ).fetchall()

        result = []
        for row in rows:
            try:
                result.append({
                    "alert_id": row["alert_id"],
                    "alert_type": row["alert_type"],
                    "severity": row["severity"],
                    "timestamp": row["timestamp"],
                    "node_ids": json.loads(row["node_ids"] or "[]"),
                    "description": row["description"] or "",
                    "evidence": json.loads(row["evidence"] or "{}"),
                    "confidence": row["confidence"] or 0.0,
                    "status": row["status"],
                    "auto_response": row["auto_response"],
                })
            except Exception as exc:
                logger.debug("Failed to parse alert row: %s", exc)
        return result

    def get_alert(self, alert_id: str) -> Optional[Dict]:
        """Return a single alert by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM alerts WHERE alert_id = ?", (alert_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return {
                "alert_id": row["alert_id"],
                "alert_type": row["alert_type"],
                "severity": row["severity"],
                "timestamp": row["timestamp"],
                "node_ids": json.loads(row["node_ids"] or "[]"),
                "description": row["description"] or "",
                "evidence": json.loads(row["evidence"] or "{}"),
                "confidence": row["confidence"] or 0.0,
                "status": row["status"],
                "auto_response": row["auto_response"],
            }
        except Exception:
            return None

    def close_alert(self, alert_id: str, resolution: str) -> bool:
        """Close an alert with a resolution reason."""
        valid_resolutions = {"mitigated", "false_positive", "investigating"}
        if resolution not in valid_resolutions:
            resolution = "mitigated"
        try:
            with self._conn() as conn:
                rowcount = conn.execute(
                    "UPDATE alerts SET status = ? WHERE alert_id = ?",
                    (resolution, alert_id),
                ).rowcount
            # Also update in-memory history
            for alert in self.alert_history:
                if alert.alert_id == alert_id:
                    alert.status = resolution
            return rowcount > 0
        except Exception as exc:
            logger.warning("close_alert failed: %s", exc)
            return False

    def get_all_actions(self) -> List[Dict]:
        """Return all defence actions from DB."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM defense_actions ORDER BY executed_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            try:
                result.append({
                    "action_id": row["action_id"],
                    "alert_id": row["alert_id"],
                    "action_type": row["action_type"],
                    "target_node": row["target_node"],
                    "status": row["status"],
                    "executed_at": row["executed_at"],
                    "result": row["result"],
                })
            except Exception:
                pass
        return result

    def get_action(self, action_id: str) -> Optional[Dict]:
        """Return a single action by ID."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM defense_actions WHERE action_id = ?", (action_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "action_id": row["action_id"],
            "alert_id": row["alert_id"],
            "action_type": row["action_type"],
            "target_node": row["target_node"],
            "status": row["status"],
            "executed_at": row["executed_at"],
            "result": row["result"],
        }

    def get_status(self) -> Dict:
        """Return detector status for the API."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
            open_count = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE status = 'open'"
            ).fetchone()[0]
            mitigated = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE status = 'mitigated'"
            ).fetchone()[0]

        return {
            "enabled": _cfg_enabled(),
            "running": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "total_alerts": total,
            "open_alerts": open_count,
            "mitigated_alerts": mitigated,
            "interval_seconds": _cfg_interval(),
            "auto_respond": _cfg_auto_respond(),
        }

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """
        Background coroutine: run ``detect_attacks()`` every
        ``VEIL_DETECTOR_INTERVAL`` seconds.
        Should be wrapped in ``asyncio.create_task()``.
        """
        interval = _cfg_interval()
        logger.info("AttackDetector loop started (interval=%ds)", interval)
        # Initial delay — wait for the collector to warm up
        await asyncio.sleep(60)
        self._running = True

        while True:
            if _cfg_enabled():
                try:
                    alerts = await self.detect_attacks()
                    logger.info(
                        "Detector cycle complete | new_alerts=%d open=%d",
                        len(alerts),
                        len(self.get_open_alerts()),
                    )
                except Exception as exc:
                    logger.warning("Detector cycle failed: %s", exc)
            else:
                logger.debug("Detector disabled — skipping cycle")
            await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

attack_detector = AttackDetector()
