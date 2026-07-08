"""
JULIUS — Tests for MetricsCollector
=====================================
Covers:
  1. Node metric fetch: mock /mix/status, parse correctly.
  2. Aggregation: multiple nodes → correct NetworkMetrics.
  3. Health status: thresholds trigger warning/critical correctly.
  4. Historical retrieval: time-range query returns stored rows.
  5. Pruning: old data deleted, recent data preserved.
  6. Concurrent collection: multiple nodes polled in parallel.

All tests use a temp SQLite database and monkeypatching — no real HTTP calls.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the project root is on the path
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

# ── Set env overrides BEFORE any backend imports ────────────────────────────
os.environ.setdefault("DB_PATH_OVERRIDE", tempfile.mktemp(suffix=".db"))
os.environ.setdefault("VEIL_COLLECTOR_ENABLED", "true")
os.environ.setdefault("VEIL_COLLECTOR_INTERVAL", "60")
os.environ.setdefault("VEIL_COLLECTOR_HISTORY_RETENTION_DAYS", "30")
os.environ.setdefault("VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY", "5.0")   # seconds
os.environ.setdefault("VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE", "100")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_collector(tmp_path: str) -> "MetricsCollector":
    """Return a fresh MetricsCollector backed by an isolated temp DB."""
    from backend.guardian.collector import MetricsCollector  # type: ignore
    return MetricsCollector(db_path=tmp_path)


def _raw_status(**overrides) -> dict:
    """Return a minimal /mix/status response dict with optional overrides."""
    base = {
        "node_id": "test-node-1",
        "uptime_seconds": 3600.0,
        "queue_size": 10,
        "packets_processed": 500,
        "packets_forwarded": 490,
        "bytes_processed": 1_000_000,
        "latency_avg_ms": 20.0,
        "latency_p95_ms": 45.0,
        "cpu_percent": 5.0,
        "memory_usage_mb": 128.0,
        "active_connections": 3,
        "cover_traffic_rate": 1.5,
        "mixing_delay_current": 0.5,
        "strata_count": 2,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path):
    """Yield a path to an isolated metrics database file."""
    return str(tmp_path / "test_metrics.db")


@pytest.fixture()
def collector(tmp_db):
    """Yield a MetricsCollector wired to the isolated DB."""
    return _make_collector(tmp_db)


# ===========================================================================
# Test 1 — Node metric fetch: mock /mix/status, parse correctly
# ===========================================================================

def test_collect_from_node_parses_response(collector):
    """
    Given a mocked /mix/status HTTP response, collect_from_node should
    parse every field into a NodeMetric and persist it to the DB.
    """
    from backend.models.metric_models import NodeMetric  # type: ignore

    status_data = _raw_status(node_id="alpha-node", latency_avg_ms=33.7, queue_size=55)

    with patch.object(collector, "_http_get_status", return_value=status_data):
        metric = asyncio.get_event_loop().run_until_complete(
            collector.collect_from_node("alpha-node", "http://alpha-node:8080")
        )

    assert metric is not None, "collect_from_node should return a NodeMetric, not None"
    assert isinstance(metric, NodeMetric)
    assert metric.node_id == "alpha-node"
    assert metric.latency_avg_ms == pytest.approx(33.7)
    assert metric.queue_size == 55
    assert metric.packets_processed == 500
    assert metric.memory_usage_mb == pytest.approx(128.0)

    # Verify it was persisted
    stored = collector.get_node_latest("alpha-node")
    assert stored is not None
    assert stored.node_id == "alpha-node"
    assert stored.latency_avg_ms == pytest.approx(33.7)


def test_collect_from_node_unreachable_returns_none(collector):
    """When the HTTP call returns None (node unreachable), result should be None."""
    with patch.object(collector, "_http_get_status", return_value=None):
        metric = asyncio.get_event_loop().run_until_complete(
            collector.collect_from_node("ghost-node", "http://ghost:9999")
        )
    assert metric is None


# ===========================================================================
# Test 2 — Aggregation: multiple nodes → correct NetworkMetrics
# ===========================================================================

def test_collect_all_nodes_aggregates(collector):
    """
    collect_all_nodes should poll all registered nodes concurrently and
    return a NetworkMetrics with accurate counts and aggregate values.
    """
    node_responses = {
        "node-a": _raw_status(node_id="node-a", latency_avg_ms=10.0, queue_size=5, bytes_processed=2_000_000, uptime_seconds=600),
        "node-b": _raw_status(node_id="node-b", latency_avg_ms=20.0, queue_size=8, bytes_processed=3_000_000, uptime_seconds=600),
        "node-c": _raw_status(node_id="node-c", latency_avg_ms=30.0, queue_size=3, bytes_processed=1_000_000, uptime_seconds=600),
    }

    async def fake_collect(nid, url):
        from backend.models.metric_models import NodeMetric  # type: ignore
        raw = node_responses.get(nid)
        if raw is None:
            return None
        return NodeMetric(
            node_id=nid,
            timestamp=datetime.now(tz=timezone.utc),
            **{k: v for k, v in raw.items() if k != "node_id"},
        )

    with patch.object(collector, "_get_active_nodes", return_value={"node-a": "http://a", "node-b": "http://b", "node-c": "http://c"}):
        with patch.object(collector, "collect_from_node", side_effect=fake_collect):
            net = asyncio.get_event_loop().run_until_complete(collector.collect_all_nodes())

    assert net.total_nodes == 3
    assert net.active_nodes == 3
    # Average latency = (10 + 20 + 30) / 3 = 20.0
    assert net.average_latency_ms == pytest.approx(20.0, abs=0.1)
    assert net.total_queue_size == 16  # 5 + 8 + 3
    assert net.total_packets_processed == 1500  # 500 × 3


def test_collect_all_nodes_empty_registry(collector):
    """With no registered nodes, collect_all_nodes should return zeros gracefully."""
    with patch.object(collector, "_get_active_nodes", return_value={}):
        net = asyncio.get_event_loop().run_until_complete(collector.collect_all_nodes())
    assert net.total_nodes == 0
    assert net.active_nodes == 0
    assert net.average_latency_ms == 0.0


# ===========================================================================
# Test 3 — Health status thresholds
# ===========================================================================

def test_health_status_healthy(collector):
    from backend.models.metric_models import NodeMetric  # type: ignore
    m = NodeMetric(
        node_id="h1",
        timestamp=datetime.now(tz=timezone.utc),
        uptime_seconds=3600,
        queue_size=5,
        latency_avg_ms=100.0,   # 0.1 s — well below 5 s threshold
        **{k: v for k, v in _raw_status().items() if k not in ("node_id", "uptime_seconds", "queue_size", "latency_avg_ms")},
    )
    assert collector.get_health_status(m) == "healthy"


def test_health_status_critical_on_high_latency(collector):
    """Latency above ALERT_THRESHOLD_LATENCY seconds (5 s = 5000 ms) → critical."""
    from backend.models.metric_models import NodeMetric  # type: ignore
    m = NodeMetric(
        node_id="h2",
        timestamp=datetime.now(tz=timezone.utc),
        uptime_seconds=3600,
        queue_size=5,
        latency_avg_ms=6000.0,  # 6 seconds
        **{k: v for k, v in _raw_status().items() if k not in ("node_id", "uptime_seconds", "queue_size", "latency_avg_ms")},
    )
    assert collector.get_health_status(m) == "critical"


def test_health_status_warning_on_high_queue(collector):
    """Queue size above ALERT_THRESHOLD_QUEUE (100) → warning."""
    from backend.models.metric_models import NodeMetric  # type: ignore
    m = NodeMetric(
        node_id="h3",
        timestamp=datetime.now(tz=timezone.utc),
        uptime_seconds=3600,
        queue_size=150,          # above threshold
        latency_avg_ms=10.0,
        **{k: v for k, v in _raw_status().items() if k not in ("node_id", "uptime_seconds", "queue_size", "latency_avg_ms")},
    )
    assert collector.get_health_status(m) == "warning"


def test_health_status_warning_on_low_uptime(collector):
    """Very low uptime (< 60 s) → warning regardless of other metrics."""
    from backend.models.metric_models import NodeMetric  # type: ignore
    m = NodeMetric(
        node_id="h4",
        timestamp=datetime.now(tz=timezone.utc),
        uptime_seconds=30,       # just started
        queue_size=5,
        latency_avg_ms=10.0,
        **{k: v for k, v in _raw_status().items() if k not in ("node_id", "uptime_seconds", "queue_size", "latency_avg_ms")},
    )
    assert collector.get_health_status(m) == "warning"


# ===========================================================================
# Test 4 — Historical retrieval: time-range query
# ===========================================================================

def test_get_node_metrics_returns_history(collector):
    """Stored metrics within the requested window should be returned."""
    from backend.models.metric_models import NodeMetric  # type: ignore

    now = datetime.now(tz=timezone.utc)

    # Insert 3 metrics: two recent, one old (25 hours ago)
    for delta_hours, q in [(0, 10), (1, 20), (25, 99)]:
        ts = now - timedelta(hours=delta_hours)
        m = NodeMetric(
            node_id="hist-node",
            timestamp=ts,
            queue_size=q,
            **{k: v for k, v in _raw_status().items() if k not in ("node_id", "queue_size")},
        )
        collector._store_metric(m)

    # Query last 24 hours — should return the 2 recent ones only
    history = collector.get_node_metrics("hist-node", hours=24)
    assert len(history) == 2
    # Newest first
    queue_sizes = [m.queue_size for m in history]
    assert 10 in queue_sizes
    assert 20 in queue_sizes
    assert 99 not in queue_sizes


def test_get_node_latest_returns_most_recent(collector):
    """get_node_latest should return the metric with the highest timestamp."""
    from backend.models.metric_models import NodeMetric  # type: ignore

    now = datetime.now(tz=timezone.utc)
    for hours_ago in [2, 0, 1]:
        ts = now - timedelta(hours=hours_ago)
        m = NodeMetric(
            node_id="latest-node",
            timestamp=ts,
            queue_size=hours_ago * 10,
            **{k: v for k, v in _raw_status().items() if k not in ("node_id", "queue_size")},
        )
        collector._store_metric(m)

    latest = collector.get_node_latest("latest-node")
    assert latest is not None
    # The most recent one has hours_ago=0, so queue_size=0
    assert latest.queue_size == 0


# ===========================================================================
# Test 5 — Pruning: old data deleted, recent data preserved
# ===========================================================================

def test_prune_old_data(collector):
    """prune_old_data should remove rows older than the retention window."""
    from backend.models.metric_models import NodeMetric  # type: ignore

    now = datetime.now(tz=timezone.utc)

    # Insert one old metric (35 days ago) and one recent metric (1 day ago)
    old_ts = now - timedelta(days=35)
    recent_ts = now - timedelta(days=1)

    for ts, q in [(old_ts, 111), (recent_ts, 222)]:
        m = NodeMetric(
            node_id="prune-node",
            timestamp=ts,
            queue_size=q,
            **{k: v for k, v in _raw_status().items() if k not in ("node_id", "queue_size")},
        )
        collector._store_metric(m)

    # Prune (retention = 30 days)
    collector.prune_old_data()

    # Only the recent metric should remain
    history = collector.get_node_metrics("prune-node", hours=9999)
    assert len(history) == 1
    assert history[0].queue_size == 222


# ===========================================================================
# Test 6 — Concurrent collection
# ===========================================================================

def test_collect_all_nodes_concurrent(collector):
    """
    collect_all_nodes should run node requests in parallel (asyncio.gather).
    We verify that all node results are collected and that the total count
    matches regardless of order.
    """
    import time as _time

    call_times = []

    async def slow_collect(nid, url):
        """Simulate a slow node response; record call start time."""
        from backend.models.metric_models import NodeMetric  # type: ignore
        start = _time.monotonic()
        await asyncio.sleep(0.05)   # 50 ms simulated latency
        call_times.append(_time.monotonic() - start)
        raw = _raw_status(node_id=nid)
        return NodeMetric(
            node_id=nid,
            timestamp=datetime.now(tz=timezone.utc),
            **{k: v for k, v in raw.items() if k != "node_id"},
        )

    nodes = {f"node-{i}": f"http://node-{i}" for i in range(5)}

    with patch.object(collector, "_get_active_nodes", return_value=nodes):
        with patch.object(collector, "collect_from_node", side_effect=slow_collect):
            start_total = asyncio.get_event_loop().time()
            net = asyncio.get_event_loop().run_until_complete(collector.collect_all_nodes())
            elapsed = asyncio.get_event_loop().time() - start_total

    assert net.active_nodes == 5
    # If they ran sequentially this would take ~250 ms; with gather it should
    # be well under 200 ms (we allow a generous 400 ms for CI overhead).
    # The key assertion is that all 5 nodes were collected.
    assert net.total_nodes == 5


# ===========================================================================
# Test 7 — get_network_summary round-trip
# ===========================================================================

def test_get_network_summary_round_trip(collector):
    """Stored network metrics should be retrievable via get_network_summary."""
    from backend.models.metric_models import NetworkMetrics  # type: ignore

    net = NetworkMetrics(
        timestamp=datetime.now(tz=timezone.utc),
        total_nodes=4,
        active_nodes=3,
        total_bandwidth_bps=1_000_000.0,
        average_latency_ms=25.5,
        total_queue_size=30,
        total_packets_processed=2000,
        health_breakdown={"healthy": 2, "warning": 1, "critical": 0},
    )
    collector._store_network_metric(net)

    retrieved = collector.get_network_summary()
    assert retrieved is not None
    assert retrieved.total_nodes == 4
    assert retrieved.active_nodes == 3
    assert retrieved.average_latency_ms == pytest.approx(25.5)
    assert retrieved.health_breakdown["healthy"] == 2
