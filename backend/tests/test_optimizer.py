"""
JULIUS — Tests for the AI Network Optimizer
============================================
Covers all 6 required scenarios:

1. Lambda increase  — high queue → lambda should increase.
2. Lambda decrease  — low queue + stable node → lambda should decrease.
3. Strata increase  — active nodes below anonymity threshold → strata goes up.
4. Cover adjustment — low traffic → cover ratio should increase.
5. Reroute trigger  — high latency → reroute decision is produced.
6. End-to-end       — optimizer.optimize() runs and returns a report.
"""

from __future__ import annotations

import os
import sys
import types
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — allow running as: python -m pytest backend/tests/test_optimizer.py
# ---------------------------------------------------------------------------
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# Set env vars before importing backend modules
os.environ.setdefault("JULIUS_DEBUG", "0")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("VEIL_OPTIMIZER_ENABLED", "true")
os.environ.setdefault("VEIL_OPTIMIZER_INTERVAL", "300")
os.environ.setdefault("VEIL_OPTIMIZER_LAMBDA_MIN", "0.05")
os.environ.setdefault("VEIL_OPTIMIZER_LAMBDA_MAX", "0.5")
os.environ.setdefault("VEIL_OPTIMIZER_STRATA_MIN", "3")
os.environ.setdefault("VEIL_OPTIMIZER_STRATA_MAX", "5")
os.environ.setdefault("VEIL_OPTIMIZER_COVER_MIN", "0.5")
os.environ.setdefault("VEIL_OPTIMIZER_COVER_MAX", "2.0")
os.environ.setdefault("VEIL_OPTIMIZER_ANONYMITY_THRESHOLD", "100")

# ---------------------------------------------------------------------------
# Helpers — build NodeMetric stubs
# ---------------------------------------------------------------------------

from backend.models.metric_models import NodeMetric  # noqa: E402
from backend.models.optimization_models import OptimizationDecision  # noqa: E402


def _make_metric(
    node_id: str = "node-test",
    queue_size: int = 0,
    latency_avg_ms: float = 100.0,
    uptime_seconds: float = 7200.0,
    packets_processed: int = 1000,
    cover_traffic_rate: float = 1.0,
    mixing_delay_current: float = 0.1,
    strata_count: int = 3,
) -> NodeMetric:
    return NodeMetric(
        node_id=node_id,
        timestamp=datetime.now(tz=timezone.utc),
        uptime_seconds=uptime_seconds,
        queue_size=queue_size,
        packets_processed=packets_processed,
        packets_forwarded=packets_processed,
        bytes_processed=packets_processed * 512,
        latency_avg_ms=latency_avg_ms,
        latency_p95_ms=latency_avg_ms * 1.5,
        cpu_percent=10.0,
        memory_usage_mb=128.0,
        active_connections=5,
        cover_traffic_rate=cover_traffic_rate,
        mixing_delay_current=mixing_delay_current,
        strata_count=strata_count,
    )


# ---------------------------------------------------------------------------
# Helper — create a fresh NetworkOptimizer with a mocked collector
# ---------------------------------------------------------------------------

def _make_optimizer(node_ids: Optional[List[str]] = None, node_metrics: Optional[dict] = None):
    """
    Return a NetworkOptimizer with its internal collector replaced by a mock,
    so no real SQLite DB or HTTP requests are made.
    """
    from backend.guardian.optimizer import NetworkOptimizer

    mock_collector = MagicMock()
    mock_collector.get_all_node_ids.return_value = node_ids or []
    mock_collector.get_network_summary.return_value = None

    if node_metrics:
        mock_collector.get_node_latest.side_effect = lambda nid: node_metrics.get(nid)
    else:
        mock_collector.get_node_latest.return_value = None

    opt = NetworkOptimizer.__new__(NetworkOptimizer)
    opt._collector = mock_collector
    opt._decision_log = __import__("collections").deque(maxlen=500)
    opt._total_cycles = 0
    opt._total_applied = 0
    opt._last_run = None
    opt._last_report = None
    return opt


# ===========================================================================
# 1. Lambda increase — high queue → lambda should increase
# ===========================================================================

class TestLambdaIncrease:
    def test_high_queue_produces_increase_lambda_decision(self):
        """Queue depth > 50 should trigger an 'adjust_lambda' decision that raises λ."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-A",
            queue_size=75,          # > 50 threshold
            mixing_delay_current=0.1,
        )

        decisions = opt._evaluate_node(metric, active_node_count=10)

        lambda_decisions = [d for d in decisions if d.action_type == "adjust_lambda"]
        assert lambda_decisions, "Expected at least one adjust_lambda decision"

        decision = lambda_decisions[0]
        assert decision.new_value > decision.previous_value, (
            f"Expected lambda to increase: {decision.previous_value} → {decision.new_value}"
        )
        assert decision.new_value <= float(os.environ["VEIL_OPTIMIZER_LAMBDA_MAX"]), (
            "new_value must not exceed LAMBDA_MAX"
        )
        assert "anonymity" in decision.reason.lower() or "queue" in decision.reason.lower()

    def test_high_queue_confidence_scales_with_severity(self):
        """Confidence should be higher when queue is much larger than the threshold."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric_mild = _make_metric(queue_size=55, mixing_delay_current=0.1)
        metric_severe = _make_metric(queue_size=200, mixing_delay_current=0.1)

        decisions_mild = opt._evaluate_node(metric_mild, 10)
        decisions_severe = opt._evaluate_node(metric_severe, 10)

        conf_mild = next(
            (d.confidence for d in decisions_mild if d.action_type == "adjust_lambda"), 0.0
        )
        conf_severe = next(
            (d.confidence for d in decisions_severe if d.action_type == "adjust_lambda"), 0.0
        )
        assert conf_severe >= conf_mild, (
            "Severe queue overload should yield higher confidence than mild overload"
        )


# ===========================================================================
# 2. Lambda decrease — low queue + stable node → lambda should decrease
# ===========================================================================

class TestLambdaReduction:
    def test_low_queue_stable_node_reduces_lambda(self):
        """Queue < 10 and uptime > 1 h should lower λ for better performance."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-B",
            queue_size=3,           # < 10 threshold
            uptime_seconds=7200,    # > 3600 s
            mixing_delay_current=0.3,
        )

        decisions = opt._evaluate_node(metric, active_node_count=10)

        lambda_decisions = [d for d in decisions if d.action_type == "adjust_lambda"]
        assert lambda_decisions, "Expected an adjust_lambda decision for low-traffic node"

        decision = lambda_decisions[0]
        assert decision.new_value < decision.previous_value, (
            f"Expected lambda to decrease: {decision.previous_value} → {decision.new_value}"
        )
        assert decision.new_value >= float(os.environ["VEIL_OPTIMIZER_LAMBDA_MIN"]), (
            "new_value must not go below LAMBDA_MIN"
        )

    def test_low_queue_new_node_does_not_reduce_lambda(self):
        """Node with < 1 h uptime should NOT have its lambda reduced even with low queue."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-new",
            queue_size=3,
            uptime_seconds=120,     # < 3600 s — node too new
            mixing_delay_current=0.3,
        )

        decisions = opt._evaluate_node(metric, active_node_count=10)
        reduce_decisions = [
            d for d in decisions
            if d.action_type == "adjust_lambda" and d.new_value < d.previous_value
        ]
        assert not reduce_decisions, (
            "Should NOT reduce lambda for a newly-started node"
        )


# ===========================================================================
# 3. Strata increase — low anonymity → increase strata
# ===========================================================================

class TestStrataAdjustment:
    def test_low_active_nodes_increases_strata(self):
        """When active nodes < ANONYMITY_THRESHOLD, strata count should increase."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        # Threshold is 100 from env; pass only 5 active nodes
        metric = _make_metric(
            node_id="node-C",
            strata_count=3,
        )

        decisions = opt._evaluate_node(metric, active_node_count=5)

        strata_decisions = [d for d in decisions if d.action_type == "adjust_strata"]
        assert strata_decisions, "Expected adjust_strata decision when nodes < threshold"

        decision = strata_decisions[0]
        assert decision.new_value > decision.previous_value, (
            f"Expected strata to increase: {decision.previous_value} → {decision.new_value}"
        )

    def test_sufficient_nodes_may_reduce_strata(self):
        """When active nodes >= ANONYMITY_THRESHOLD with high strata, strata can be reduced."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-D",
            strata_count=5,         # at max
        )

        # 200 active nodes > threshold of 100
        decisions = opt._evaluate_node(metric, active_node_count=200)

        strata_decisions = [d for d in decisions if d.action_type == "adjust_strata"]
        assert strata_decisions, "Expected strata reduction when nodes exceed threshold"

        decision = strata_decisions[0]
        assert decision.new_value < decision.previous_value


# ===========================================================================
# 4. Cover adjustment — low traffic → increase cover
# ===========================================================================

class TestCoverAdjustment:
    def test_low_traffic_increases_cover_ratio(self):
        """Fewer than 100 packets should trigger cover ratio increase."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-E",
            packets_processed=10,   # < 100 threshold
            cover_traffic_rate=0.5,
        )

        decisions = opt._evaluate_node(metric, active_node_count=10)

        cover_decisions = [d for d in decisions if d.action_type == "adjust_cover_rate"]
        assert cover_decisions, "Expected adjust_cover_rate for low-traffic node"

        decision = cover_decisions[0]
        assert decision.new_value > decision.previous_value, (
            f"Expected cover ratio to increase: {decision.previous_value} → {decision.new_value}"
        )
        assert decision.new_value <= float(os.environ["VEIL_OPTIMIZER_COVER_MAX"]), (
            "Cover ratio must not exceed COVER_MAX"
        )

    def test_excessive_cover_ratio_is_capped(self):
        """A cover ratio above COVER_MAX should be reduced to the max value."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-F",
            packets_processed=5000,
            cover_traffic_rate=10.0,    # well above max of 2.0
        )

        decisions = opt._evaluate_node(metric, active_node_count=10)

        cover_decisions = [d for d in decisions if d.action_type == "adjust_cover_rate"]
        assert cover_decisions, "Expected decision to reduce excessive cover ratio"

        decision = cover_decisions[0]
        assert decision.new_value <= float(os.environ["VEIL_OPTIMIZER_COVER_MAX"])


# ===========================================================================
# 5. Rerouting — high latency → reroute decision
# ===========================================================================

class TestRerouting:
    def test_high_latency_triggers_reroute(self):
        """Latency above 2000 ms should produce a 'reroute_traffic' decision."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-G",
            latency_avg_ms=5000.0,  # > 2000 ms threshold
        )

        decisions = opt._evaluate_node(metric, active_node_count=50)

        reroute_decisions = [d for d in decisions if d.action_type == "reroute_traffic"]
        assert reroute_decisions, "Expected reroute_traffic decision for high-latency node"

        decision = reroute_decisions[0]
        assert decision.previous_value == pytest.approx(5000.0)
        assert "latency" in decision.reason.lower() or "reroute" in decision.reason.lower()

    def test_normal_latency_no_reroute(self):
        """Normal latency should NOT trigger any reroute decision."""
        from backend.guardian.optimizer import NetworkOptimizer

        opt = _make_optimizer()
        metric = _make_metric(
            node_id="node-H",
            latency_avg_ms=200.0,   # well below threshold
        )

        decisions = opt._evaluate_node(metric, active_node_count=50)
        reroute_decisions = [d for d in decisions if d.action_type == "reroute_traffic"]
        assert not reroute_decisions, "Should NOT reroute when latency is normal"


# ===========================================================================
# 6. End-to-end — optimizer.optimize() runs and returns a report
# ===========================================================================

class TestEndToEnd:
    def test_optimize_returns_report_with_no_nodes(self):
        """optimize() with zero nodes should still return a valid OptimizationReport."""
        from backend.models.optimization_models import OptimizationReport

        opt = _make_optimizer(node_ids=[], node_metrics={})

        async def _noop_apply(decisions):
            return []

        opt._apply_decisions = _noop_apply

        report = asyncio.run(opt.optimize())

        assert isinstance(report, OptimizationReport)
        assert report.nodes_evaluated == 0
        assert report.decisions_applied == 0
        assert opt._total_cycles == 1

    def test_optimize_evaluates_all_nodes(self):
        """optimize() should evaluate every node returned by the collector."""
        from backend.models.optimization_models import OptimizationReport

        metrics = {
            "node-1": _make_metric("node-1", queue_size=75),
            "node-2": _make_metric("node-2", queue_size=3, uptime_seconds=7200),
            "node-3": _make_metric("node-3", latency_avg_ms=9000),
        }
        opt = _make_optimizer(node_ids=list(metrics.keys()), node_metrics=metrics)

        async def _fake_apply(decisions):
            for d in decisions:
                d.applied = True
            return decisions

        opt._apply_decisions = _fake_apply

        report = asyncio.run(opt.optimize())

        assert isinstance(report, OptimizationReport)
        assert report.nodes_evaluated == 3
        assert report.decisions_applied > 0, "Expected some decisions to be applied"

    def test_optimize_increments_cycle_counter(self):
        """Each call to optimize() should increment the internal cycle counter."""
        opt = _make_optimizer()

        async def _noop(decisions):
            return []

        opt._apply_decisions = _noop

        assert opt._total_cycles == 0
        asyncio.run(opt.optimize())
        assert opt._total_cycles == 1
        asyncio.run(opt.optimize())
        assert opt._total_cycles == 2

    def test_optimize_logs_decisions_to_rolling_log(self):
        """Applied decisions should appear in get_recent_decisions()."""
        metrics = {"node-log": _make_metric("node-log", queue_size=80)}
        opt = _make_optimizer(node_ids=["node-log"], node_metrics=metrics)

        async def _fake_apply(decisions):
            for d in decisions:
                d.applied = True
            return decisions

        opt._apply_decisions = _fake_apply

        asyncio.run(opt.optimize())

        recent = opt.get_recent_decisions(limit=100)
        assert len(recent) > 0, "Decisions should appear in the rolling log after optimize()"
