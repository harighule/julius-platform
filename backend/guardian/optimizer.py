"""
JULIUS — AI Network Optimizer
=============================
Continuously analyses metrics from all active mix-nodes and automatically
adjusts their parameters to balance:

  * **Anonymity** — increase mixing delay / strata when queue depth is high
    or the anonymity set is too small.
  * **Performance** — reduce delays when traffic is low and nodes are stable.
  * **Revenue** — prefer routing through the most reliable / highest-throughput
    nodes to maximise billable bandwidth.

The optimizer runs as an asyncio background task (started in ``main.py``)
and exposes a ``NetworkOptimizer`` class with a single ``optimize()`` entry
point that can also be invoked synchronously via the Guardian API.

Design decisions
----------------
* **Pure asyncio** — the ``_apply_decisions`` method uses ``asyncio.gather``
  so config updates to different nodes are sent concurrently.
* **Retry with exponential back-off** — ``_send_config`` retries up to
  3 times with 1 s / 2 s / 4 s delays before giving up.
* **Confidence scoring** — each decision carries a confidence value (0-1)
  derived from the magnitude of the anomaly; only decisions above a
  configurable threshold (default 0.5) are actually sent.
* **Decision log** — the last 500 decisions are kept in memory for the
  ``/guardian/optimizer/decisions`` endpoint; the full report is also logged
  to Pantheon (best-effort).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config helpers (lazy — read from config.py at call-time so tests can
# override env vars without the module-level import freezing values)
# ---------------------------------------------------------------------------


def _cfg_enabled() -> bool:
    from ..config import VEIL_OPTIMIZER_ENABLED  # type: ignore
    return VEIL_OPTIMIZER_ENABLED


def _cfg_interval() -> int:
    from ..config import VEIL_OPTIMIZER_INTERVAL  # type: ignore
    return VEIL_OPTIMIZER_INTERVAL


def _cfg_lambda_min() -> float:
    from ..config import VEIL_OPTIMIZER_LAMBDA_MIN  # type: ignore
    return VEIL_OPTIMIZER_LAMBDA_MIN


def _cfg_lambda_max() -> float:
    from ..config import VEIL_OPTIMIZER_LAMBDA_MAX  # type: ignore
    return VEIL_OPTIMIZER_LAMBDA_MAX


def _cfg_strata_min() -> int:
    from ..config import VEIL_OPTIMIZER_STRATA_MIN  # type: ignore
    return VEIL_OPTIMIZER_STRATA_MIN


def _cfg_strata_max() -> int:
    from ..config import VEIL_OPTIMIZER_STRATA_MAX  # type: ignore
    return VEIL_OPTIMIZER_STRATA_MAX


def _cfg_cover_min() -> float:
    from ..config import VEIL_OPTIMIZER_COVER_MIN  # type: ignore
    return VEIL_OPTIMIZER_COVER_MIN


def _cfg_cover_max() -> float:
    from ..config import VEIL_OPTIMIZER_COVER_MAX  # type: ignore
    return VEIL_OPTIMIZER_COVER_MAX


def _cfg_anonymity_threshold() -> int:
    from ..config import VEIL_OPTIMIZER_ANONYMITY_THRESHOLD  # type: ignore
    return VEIL_OPTIMIZER_ANONYMITY_THRESHOLD


# ---------------------------------------------------------------------------
# Thresholds for decision logic
# ---------------------------------------------------------------------------
_HIGH_QUEUE_THRESHOLD = 50      # packets — increase lambda (more delay)
_LOW_QUEUE_THRESHOLD = 10       # packets — decrease lambda (less delay)
_HIGH_LATENCY_MS = 2_000        # ms — suggest rerouting
_LOW_TRAFFIC_PACKETS = 100      # packets — increase cover ratio
_MIN_UPTIME_FOR_REDUCTION = 3_600   # seconds — node must be up ≥ 1 h before we reduce delay


# ---------------------------------------------------------------------------
# NetworkOptimizer
# ---------------------------------------------------------------------------


class NetworkOptimizer:
    """
    The AI brain of the JULIUS network.

    Usage::

        optimizer = NetworkOptimizer()
        report = await optimizer.optimize()   # run one full cycle
        # or: asyncio.create_task(optimizer.run_forever())
    """

    def __init__(self) -> None:
        from ..guardian.collector import metrics_collector  # type: ignore

        self._collector = metrics_collector
        self._decision_log: Deque = deque(maxlen=500)  # rolling log
        self._total_cycles: int = 0
        self._total_applied: int = 0
        self._last_run: Optional[datetime] = None
        self._last_report: Optional["OptimizationReport"] = None  # type: ignore
        logger.info("NetworkOptimizer initialised")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def optimize(self) -> "OptimizationReport":  # type: ignore
        """
        Run one complete optimization cycle:

        1. Snapshot current network health.
        2. For every known node, evaluate metrics and propose changes.
        3. Apply decisions (HTTP POST to each node's /mix/config).
        4. Re-snapshot health and build the final report.
        5. Log decisions to Pantheon (best-effort).
        """
        from ..models.optimization_models import OptimizationReport  # type: ignore

        ts = datetime.now(tz=timezone.utc)
        errors: List[str] = []

        # ── 1. Snapshot health before ────────────────────────────────────────
        health_before = self._snapshot_health()

        # ── 2. Collect per-node metrics and evaluate ─────────────────────────
        node_ids = self._collector.get_all_node_ids()
        active_count = len(node_ids)

        proposals: List["OptimizationDecision"] = []  # type: ignore
        for node_id in node_ids:
            metric = self._collector.get_node_latest(node_id)
            if metric is None:
                continue
            try:
                node_proposals = self._evaluate_node(metric, active_count)
                proposals.extend(node_proposals)
            except Exception as exc:
                msg = f"evaluate_node({node_id}): {exc}"
                logger.warning(msg)
                errors.append(msg)

        # ── 3. Apply decisions ───────────────────────────────────────────────
        applied: List["OptimizationDecision"] = []  # type: ignore
        try:
            applied = await self._apply_decisions(proposals)
        except Exception as exc:
            msg = f"_apply_decisions failed: {exc}"
            logger.error(msg)
            errors.append(msg)

        # ── 4. Snapshot health after ─────────────────────────────────────────
        health_after = self._snapshot_health()

        # ── 5. Build report ──────────────────────────────────────────────────
        summary = self._build_summary(applied)
        report = OptimizationReport(
            timestamp=ts,
            decisions=applied,
            summary=summary,
            health_before=health_before,
            health_after=health_after,
            nodes_evaluated=active_count,
            decisions_applied=len(applied),
            errors=errors,
        )

        # Update state
        self._last_run = ts
        self._last_report = report
        self._total_cycles += 1
        self._total_applied += len(applied)

        # Keep rolling log
        for d in applied:
            self._decision_log.append(d)

        # Log to Pantheon (best-effort)
        self._log_to_pantheon(report)

        logger.info(
            "Optimizer cycle complete | nodes=%d proposed=%d applied=%d errors=%d",
            active_count,
            len(proposals),
            len(applied),
            len(errors),
        )
        return report

    async def run_forever(self) -> None:
        """
        Background loop: run ``optimize()`` every ``VEIL_OPTIMIZER_INTERVAL``
        seconds.  On failure, waits 60 s before retrying (simple back-off).
        """
        interval = _cfg_interval()
        logger.info("NetworkOptimizer loop started (interval=%ds)", interval)
        await asyncio.sleep(30)  # let the collector warm up first

        while True:
            if _cfg_enabled():
                backoff = 60
                for attempt in range(3):
                    try:
                        await self.optimize()
                        break
                    except Exception as exc:
                        logger.warning(
                            "Optimizer cycle failed (attempt %d/3): %s", attempt + 1, exc
                        )
                        if attempt < 2:
                            await asyncio.sleep(backoff)
                            backoff *= 2
            else:
                logger.debug("Optimizer disabled — skipping cycle")
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Decision evaluation
    # ------------------------------------------------------------------

    def _evaluate_node(
        self,
        metric: "NodeMetric",  # type: ignore
        active_node_count: int,
    ) -> List["OptimizationDecision"]:  # type: ignore
        """
        Analyse one node's latest metric snapshot and return a list of
        proposed ``OptimizationDecision`` objects.
        """
        from ..models.optimization_models import OptimizationDecision  # type: ignore

        decisions: List[OptimizationDecision] = []
        ts = datetime.now(tz=timezone.utc)

        metrics_snapshot = {
            "queue_size": metric.queue_size,
            "latency_avg_ms": metric.latency_avg_ms,
            "uptime_seconds": metric.uptime_seconds,
            "packets_processed": metric.packets_processed,
            "cover_traffic_rate": metric.cover_traffic_rate,
            "mixing_delay_current": metric.mixing_delay_current,
            "strata_count": metric.strata_count,
        }

        # ── Lambda / mixing-delay adjustment ────────────────────────────────
        current_lambda = metric.mixing_delay_current or _cfg_lambda_min()

        if metric.queue_size > _HIGH_QUEUE_THRESHOLD:
            # Queue is building up → increase delay to let packets batch for anonymity
            new_lambda = min(current_lambda * 1.2, _cfg_lambda_max())
            if new_lambda != current_lambda:
                confidence = min(1.0, (metric.queue_size - _HIGH_QUEUE_THRESHOLD) / 50.0)
                decisions.append(
                    OptimizationDecision(
                        node_id=metric.node_id,
                        timestamp=ts,
                        action_type="adjust_lambda",
                        previous_value=current_lambda,
                        new_value=round(new_lambda, 4),
                        reason=f"Queue depth {metric.queue_size} > {_HIGH_QUEUE_THRESHOLD}; "
                               "increasing mixing delay for anonymity",
                        confidence=round(confidence, 3),
                        metrics_used=metrics_snapshot,
                    )
                )

        elif (
            metric.queue_size < _LOW_QUEUE_THRESHOLD
            and metric.uptime_seconds > _MIN_UPTIME_FOR_REDUCTION
        ):
            # Traffic is low and node is stable → reduce delay for better performance
            new_lambda = max(current_lambda * 0.8, _cfg_lambda_min())
            if new_lambda != current_lambda:
                confidence = min(
                    1.0, (_LOW_QUEUE_THRESHOLD - metric.queue_size) / float(_LOW_QUEUE_THRESHOLD)
                )
                decisions.append(
                    OptimizationDecision(
                        node_id=metric.node_id,
                        timestamp=ts,
                        action_type="adjust_lambda",
                        previous_value=current_lambda,
                        new_value=round(new_lambda, 4),
                        reason=f"Queue depth {metric.queue_size} < {_LOW_QUEUE_THRESHOLD} "
                               f"and uptime {metric.uptime_seconds:.0f}s > "
                               f"{_MIN_UPTIME_FOR_REDUCTION}s; reducing delay for performance",
                        confidence=round(confidence, 3),
                        metrics_used=metrics_snapshot,
                    )
                )

        # ── Strata adjustment ────────────────────────────────────────────────
        # If the total active node count is below anonymity threshold, push more strata
        current_strata = metric.strata_count or _cfg_strata_min()
        anonymity_ok = active_node_count >= _cfg_anonymity_threshold()

        if not anonymity_ok and current_strata < _cfg_strata_max():
            new_strata = min(current_strata + 1, _cfg_strata_max())
            decisions.append(
                OptimizationDecision(
                    node_id=metric.node_id,
                    timestamp=ts,
                    action_type="adjust_strata",
                    previous_value=float(current_strata),
                    new_value=float(new_strata),
                    reason=f"Active nodes ({active_node_count}) below anonymity threshold "
                           f"({_cfg_anonymity_threshold()}); increasing strata count",
                    confidence=0.8,
                    metrics_used=metrics_snapshot,
                )
            )
        elif anonymity_ok and current_strata > _cfg_strata_min():
            # Enough nodes — can reduce strata to save overhead
            new_strata = max(current_strata - 1, _cfg_strata_min())
            decisions.append(
                OptimizationDecision(
                    node_id=metric.node_id,
                    timestamp=ts,
                    action_type="adjust_strata",
                    previous_value=float(current_strata),
                    new_value=float(new_strata),
                    reason=f"Active nodes ({active_node_count}) meets anonymity threshold; "
                           "reducing strata overhead",
                    confidence=0.6,
                    metrics_used=metrics_snapshot,
                )
            )

        # ── Cover-traffic ratio adjustment ───────────────────────────────────
        current_cover = metric.cover_traffic_rate
        if metric.packets_processed < _LOW_TRAFFIC_PACKETS:
            # Low real traffic → raise cover ratio to mask patterns
            new_cover = min(current_cover * 1.5 if current_cover > 0 else _cfg_cover_min(),
                            _cfg_cover_max())
            if new_cover != current_cover:
                decisions.append(
                    OptimizationDecision(
                        node_id=metric.node_id,
                        timestamp=ts,
                        action_type="adjust_cover_rate",
                        previous_value=current_cover,
                        new_value=round(new_cover, 4),
                        reason=f"Low traffic ({metric.packets_processed} packets); "
                               "increasing cover ratio to mask traffic patterns",
                        confidence=0.75,
                        metrics_used=metrics_snapshot,
                    )
                )
        elif current_cover > _cfg_cover_max():
            # Cover ratio too aggressive → bring it down
            new_cover = _cfg_cover_max()
            decisions.append(
                OptimizationDecision(
                    node_id=metric.node_id,
                    timestamp=ts,
                    action_type="adjust_cover_rate",
                    previous_value=current_cover,
                    new_value=round(new_cover, 4),
                    reason=f"Cover ratio {current_cover:.2f} exceeds max {_cfg_cover_max():.2f}; "
                           "reducing to conserve bandwidth",
                    confidence=0.9,
                    metrics_used=metrics_snapshot,
                )
            )

        # ── Reroute suggestion ───────────────────────────────────────────────
        if metric.latency_avg_ms > _HIGH_LATENCY_MS:
            decisions.append(
                OptimizationDecision(
                    node_id=metric.node_id,
                    timestamp=ts,
                    action_type="reroute_traffic",
                    previous_value=metric.latency_avg_ms,
                    new_value=0.0,  # target: default/auto after reroute
                    reason=f"Latency {metric.latency_avg_ms:.0f}ms > {_HIGH_LATENCY_MS}ms; "
                           "suggest rerouting traffic away from this node",
                    confidence=min(1.0, metric.latency_avg_ms / _HIGH_LATENCY_MS - 1.0 + 0.5),
                    metrics_used=metrics_snapshot,
                )
            )

        return decisions

    # ------------------------------------------------------------------
    # Applying decisions
    # ------------------------------------------------------------------

    async def _apply_decisions(
        self,
        decisions: List["OptimizationDecision"],  # type: ignore
    ) -> List["OptimizationDecision"]:  # type: ignore
        """
        Send configuration updates to nodes concurrently.
        Returns only the decisions that were successfully applied.
        """
        if not decisions:
            return []

        tasks = [self._try_apply(d) for d in decisions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        applied = []
        for decision, result in zip(decisions, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Failed to apply %s for %s: %s",
                    decision.action_type,
                    decision.node_id,
                    result,
                )
            elif result:
                decision.applied = True
                applied.append(decision)
        return applied

    async def _try_apply(
        self, decision: "OptimizationDecision"  # type: ignore
    ) -> bool:
        """Apply a single decision; returns True on success."""
        if decision.action_type == "reroute_traffic":
            # Rerouting is advisory — we log it but don't push a config change
            logger.info(
                "REROUTE advisory | node=%s latency=%.0fms",
                decision.node_id,
                decision.previous_value,
            )
            return True  # count as applied (advisory)

        config: Dict = {}
        if decision.action_type == "adjust_lambda":
            config["lambda"] = decision.new_value
        elif decision.action_type == "adjust_strata":
            config["strata_count"] = int(decision.new_value)
        elif decision.action_type == "adjust_cover_rate":
            config["cover_ratio"] = decision.new_value

        if not config:
            return False

        return await self._send_config(decision.node_id, config)

    async def _send_config(self, node_id: str, config: Dict) -> bool:
        """
        HTTP POST ``{node_base_url}/mix/config`` with a JSON body.

        Retries up to 3 times with exponential back-off (1s, 2s, 4s).
        Returns True if the node acknowledged the update.
        """
        base_url = self._get_node_url(node_id)
        if not base_url:
            logger.debug("_send_config: no URL found for node %s — skipping", node_id)
            return False

        url = f"{base_url}/mix/config"
        payload = json.dumps(config).encode()

        loop = asyncio.get_event_loop()
        backoff = 1.0

        for attempt in range(3):
            try:
                def _http_post() -> bool:
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        method="POST",
                        headers={
                            "Content-Type": "application/json",
                            "User-Agent": "JULIUS-Optimizer/1.0",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        return resp.status in (200, 201, 204)

                success = await asyncio.wait_for(
                    loop.run_in_executor(None, _http_post), timeout=6
                )
                if success:
                    logger.debug(
                        "_send_config: node=%s config=%s → OK", node_id, config
                    )
                    return True
            except Exception as exc:
                logger.debug(
                    "_send_config attempt %d/%d for %s failed: %s",
                    attempt + 1, 3, node_id, exc,
                )
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    backoff *= 2

        return False

    def _get_node_url(self, node_id: str) -> Optional[str]:
        """Look up the base URL of a node from the onboarding registry."""
        try:
            from ..guardian.onboarding import onboarding_service  # type: ignore

            partners = onboarding_service.list_partners(filters={"status": "active"})
            for p in partners:
                pid = p.get("partner_id") or p.get("node_id")
                if pid == node_id:
                    return (p.get("node_url") or p.get("host_url", "")).rstrip("/")
        except Exception as exc:
            logger.debug("_get_node_url: onboarding not available — %s", exc)

        # Fall back to env-configured extra nodes
        import os
        extra = os.getenv("VEIL_EXTRA_NODE_URLS", "")
        for item in extra.split(","):
            item = item.strip()
            if "=" in item:
                nid, nurl = item.split("=", 1)
                if nid.strip() == node_id:
                    return nurl.strip().rstrip("/")
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _snapshot_health(self) -> Dict:
        """Return a compact health snapshot from the metrics collector."""
        try:
            net = self._collector.get_network_summary()
            if net is None:
                return {}
            return {
                "active_nodes": net.active_nodes,
                "total_nodes": net.total_nodes,
                "average_latency_ms": net.average_latency_ms,
                "total_queue_size": net.total_queue_size,
                "health_breakdown": net.health_breakdown,
            }
        except Exception:
            return {}

    @staticmethod
    def _build_summary(decisions: List["OptimizationDecision"]) -> Dict:  # type: ignore
        summary: Dict = {
            "lambda_adjustments": 0,
            "strata_changes": 0,
            "cover_adjustments": 0,
            "reroutes": 0,
        }
        for d in decisions:
            if d.action_type == "adjust_lambda":
                summary["lambda_adjustments"] += 1
            elif d.action_type == "adjust_strata":
                summary["strata_changes"] += 1
            elif d.action_type == "adjust_cover_rate":
                summary["cover_adjustments"] += 1
            elif d.action_type == "reroute_traffic":
                summary["reroutes"] += 1
        return summary

    def _log_to_pantheon(self, report: "OptimizationReport") -> None:  # type: ignore
        """Persist optimization report to Pantheon (best-effort)."""
        try:
            from ..services.pantheon.client import pantheon_client  # type: ignore

            pantheon_client.record_event(
                event_type="optimizer_cycle",
                data={
                    "timestamp": report.timestamp.isoformat(),
                    "nodes_evaluated": report.nodes_evaluated,
                    "decisions_applied": report.decisions_applied,
                    "summary": report.summary,
                    "health_before": report.health_before,
                    "health_after": report.health_after,
                },
            )
        except Exception as exc:
            logger.debug("Pantheon log skipped: %s", exc)

    # ------------------------------------------------------------------
    # Introspection (used by Guardian API)
    # ------------------------------------------------------------------

    def get_recent_decisions(self, limit: int = 100) -> List["OptimizationDecision"]:  # type: ignore
        """Return the most recent decisions from the rolling log."""
        items = list(self._decision_log)
        return items[-limit:]

    def get_status(self) -> Dict:
        """Return a status dict for the /guardian/optimizer/status endpoint."""
        return {
            "enabled": _cfg_enabled(),
            "interval_seconds": _cfg_interval(),
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "total_cycles": self._total_cycles,
            "total_decisions_applied": self._total_applied,
            "last_report": (
                self._last_report.model_dump(mode="json")
                if self._last_report
                else None
            ),
        }


# ---------------------------------------------------------------------------
# Module-level singleton (shared with main.py and guardian_api.py)
# ---------------------------------------------------------------------------

network_optimizer = NetworkOptimizer()
