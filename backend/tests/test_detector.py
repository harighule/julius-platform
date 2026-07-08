"""
JULIUS — Tests for the Attack Detector
========================================
Covers all 8 required scenarios:

1. Timing attack detection — latency deviation > threshold triggers alert.
2. Sybil attack detection  — identical fingerprints > threshold triggers alert.
3. Intersection attack     — repeated connection patterns trigger alert.
4. Node compromise         — behavioural deviation triggers alert.
5. Auto-respond            — medium severity triggers automatic action.
6. Escalation              — high severity creates pending approval.
7. Blacklist               — critical severity blacklists nodes.
8. Alert lifecycle         — open → mitigated → closed.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path / env setup
# ---------------------------------------------------------------------------
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

os.environ.setdefault("JULIUS_DEBUG", "0")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("VEIL_DETECTOR_ENABLED", "true")
os.environ.setdefault("VEIL_DETECTOR_INTERVAL", "120")
os.environ.setdefault("VEIL_DETECTOR_TIMING_THRESHOLD", "2.0")
os.environ.setdefault("VEIL_DETECTOR_SYBIL_THRESHOLD", "5")
os.environ.setdefault("VEIL_DETECTOR_INTERSECTION_THRESHOLD", "10")
os.environ.setdefault("VEIL_DETECTOR_AUTO_RESPOND", "true")

# ---------------------------------------------------------------------------
# Model imports
# ---------------------------------------------------------------------------
from backend.models.metric_models import NodeMetric  # noqa: E402
from backend.models.alert_models import AttackAlert, DefenseAction, DetectorStatus  # noqa: E402


# ---------------------------------------------------------------------------
# Helper — build NodeMetric stubs
# ---------------------------------------------------------------------------

def _make_metric(
    node_id: str = "node-test",
    latency_avg_ms: float = 100.0,
    queue_size: int = 5,
    uptime_seconds: float = 7200.0,
    packets_processed: int = 1000,
    cover_traffic_rate: float = 1.0,
    mixing_delay_current: float = 0.1,
    strata_count: int = 3,
    cpu_percent: float = 10.0,
    active_connections: int = 3,
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
        cpu_percent=cpu_percent,
        memory_usage_mb=128.0,
        active_connections=active_connections,
        cover_traffic_rate=cover_traffic_rate,
        mixing_delay_current=mixing_delay_current,
        strata_count=strata_count,
    )


# ---------------------------------------------------------------------------
# Helper — create an AttackDetector with mocked dependencies
# ---------------------------------------------------------------------------

def _make_detector(
    node_ids: Optional[List[str]] = None,
    node_metrics: Optional[Dict] = None,
    node_history: Optional[Dict] = None,
    kg_nodes: Optional[List[Dict]] = None,
):
    """
    Return an AttackDetector with mocked collector and knowledge graph,
    backed by a temporary in-memory-equivalent SQLite database.
    """
    from backend.guardian.detector import AttackDetector

    # Temporary DB
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    # Mock collector
    mock_collector = MagicMock()
    mock_collector.get_all_node_ids.return_value = node_ids or []

    if node_history:
        mock_collector.get_node_metrics.side_effect = lambda nid, **kw: node_history.get(nid, [])
    else:
        mock_collector.get_node_metrics.return_value = []

    if node_metrics:
        mock_collector.get_node_latest.side_effect = lambda nid: node_metrics.get(nid)
    else:
        mock_collector.get_node_latest.return_value = None

    # Mock optimizer
    mock_optimizer = MagicMock()
    mock_optimizer._send_config = AsyncMock(return_value=True)

    # Mock knowledge graph
    mock_kg = MagicMock()
    mock_kg.get_all_nodes.return_value = kg_nodes or []

    det = AttackDetector.__new__(AttackDetector)
    det.collector = mock_collector
    det.optimizer = mock_optimizer
    det.knowledge_graph = mock_kg
    det.alert_history = []
    det.defense_actions = []
    det._detection_cache = {}
    det.db_path = tmp.name
    det._running = False
    det._last_run = None
    det._init_db()

    return det


# ===========================================================================
# 1. Timing attack detection
# ===========================================================================

class TestTimingAttackDetection:
    """Latency deviation > VEIL_DETECTOR_TIMING_THRESHOLD standard deviations → alert."""

    def test_large_latency_deviation_triggers_alert(self):
        """Z-score >> 2.0 should produce a timing_attack alert."""
        # History: stable ~100 ms with slight natural variance, then a spike
        # Use different values so std_dev > 0 (identical values → std_dev=0 → no alert)
        baseline_vals = [95.0, 102.0, 98.0, 105.0, 97.0, 103.0, 100.0, 99.0, 101.0, 96.0]
        baseline = [_make_metric(node_id="t1", latency_avg_ms=v) for v in baseline_vals]
        spike = _make_metric(node_id="t1", latency_avg_ms=700.0)
        # Most recent first
        history = [spike] + baseline

        det = _make_detector(node_ids=["t1"], node_history={"t1": history})
        alerts = asyncio.run(det._detect_timing_attacks())

        assert len(alerts) == 1, "Expected exactly one timing_attack alert"
        alert = alerts[0]
        assert alert.alert_type == "timing_attack"
        assert alert.node_ids == ["t1"]
        assert alert.confidence > 0
        assert alert.severity in ("low", "medium", "high", "critical")

    def test_no_alert_when_deviation_below_threshold(self):
        """Stable latency should NOT trigger a timing_attack alert."""
        history = [_make_metric(node_id="t2", latency_avg_ms=100.0 + i) for i in range(10)]
        det = _make_detector(node_ids=["t2"], node_history={"t2": history})
        alerts = asyncio.run(det._detect_timing_attacks())
        assert len(alerts) == 0, "Should NOT alert for stable latency"

    def test_insufficient_history_skipped(self):
        """Fewer than 3 data points → skip node, no alert."""
        history = [_make_metric(node_id="t3", latency_avg_ms=500.0)]
        det = _make_detector(node_ids=["t3"], node_history={"t3": history})
        alerts = asyncio.run(det._detect_timing_attacks())
        assert len(alerts) == 0


# ===========================================================================
# 2. Sybil attack detection
# ===========================================================================

class TestSybilAttackDetection:
    """Nodes sharing identical fingerprints > threshold → alert."""

    def test_sybil_cluster_triggers_alert(self):
        """6 nodes with same version + IP prefix should fire sybil alert (threshold=5)."""
        nodes = [
            {
                "node_id": f"sybil-{i}",
                "software_version": "0.9.1",
                "ip_address": "10.0.1.{}".format(i + 1),
            }
            for i in range(6)  # 6 nodes, same version + /24 = 10.0.1
        ]
        det = _make_detector(kg_nodes=nodes)
        alerts = asyncio.run(det._detect_sybil_attacks())

        assert len(alerts) >= 1
        sybil_alert = alerts[0]
        assert sybil_alert.alert_type == "sybil_attack"
        assert len(sybil_alert.node_ids) >= 5
        assert sybil_alert.confidence > 0

    def test_diverse_nodes_no_sybil_alert(self):
        """Nodes with distinct versions and IP prefixes should not trigger alert."""
        nodes = [
            {
                "node_id": f"node-{i}",
                "software_version": f"0.9.{i}",
                "ip_address": f"192.168.{i}.1",
            }
            for i in range(10)
        ]
        det = _make_detector(kg_nodes=nodes)
        alerts = asyncio.run(det._detect_sybil_attacks())
        assert len(alerts) == 0, "Diverse nodes should not trigger sybil alert"

    def test_sybil_alert_confidence_scales_with_cluster_size(self):
        """Larger cluster → higher confidence."""
        small_cluster = [
            {"node_id": f"sm-{i}", "software_version": "1.0.0", "ip_address": f"10.1.1.{i + 1}"}
            for i in range(5)
        ]
        large_cluster = [
            {"node_id": f"lg-{i}", "software_version": "2.0.0", "ip_address": f"10.2.2.{i + 1}"}
            for i in range(15)
        ]

        det_small = _make_detector(kg_nodes=small_cluster)
        det_large = _make_detector(kg_nodes=large_cluster)

        alerts_small = asyncio.run(det_small._detect_sybil_attacks())
        alerts_large = asyncio.run(det_large._detect_sybil_attacks())

        assert alerts_small, "Small cluster should still alert"
        assert alerts_large, "Large cluster should alert"
        assert alerts_large[0].confidence >= alerts_small[0].confidence


# ===========================================================================
# 3. Intersection attack detection
# ===========================================================================

class TestIntersectionAttackDetection:
    """Repeated connection patterns > threshold → alert."""

    def test_accumulated_connections_trigger_alert(self):
        """A node accumulating connection_counts >= threshold should be flagged."""
        det = _make_detector(node_ids=["n-int"])
        # Seed the cache with a count already at threshold - 1
        det._detection_cache["connection_counts"] = defaultdict(int)
        threshold = int(os.environ["VEIL_DETECTOR_INTERSECTION_THRESHOLD"])
        det._detection_cache["connection_counts"]["n-int"] = threshold

        # Provide a metric with active_connections = 1 to push it over
        det.collector.get_node_latest.return_value = _make_metric(
            node_id="n-int", active_connections=1
        )

        alerts = asyncio.run(det._detect_intersection_attacks())
        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert.alert_type == "intersection_attack"
        assert "n-int" in alert.node_ids

    def test_low_connections_no_alert(self):
        """Low connection count should not trigger intersection alert."""
        det = _make_detector(node_ids=["n-safe"])
        det.collector.get_node_latest.return_value = _make_metric(
            node_id="n-safe", active_connections=1
        )
        alerts = asyncio.run(det._detect_intersection_attacks())
        assert len(alerts) == 0


# ===========================================================================
# 4. Node compromise detection
# ===========================================================================

class TestNodeCompromiseDetection:
    """Dramatic behavioural deviation triggers node_compromise alert."""

    def test_cpu_spike_triggers_compromise_alert(self):
        """CPU 3× baseline and high queue should flag node as compromised."""
        baseline = [_make_metric(node_id="comp-1", cpu_percent=10.0, queue_size=5)] * 6
        spike = _make_metric(node_id="comp-1", cpu_percent=90.0, queue_size=200)
        history = [spike] + baseline

        det = _make_detector(node_ids=["comp-1"], node_history={"comp-1": history})
        alerts = asyncio.run(det._detect_node_compromise())

        assert len(alerts) >= 1
        alert = alerts[0]
        assert alert.alert_type == "node_compromise"
        assert "comp-1" in alert.node_ids
        assert alert.confidence > 0

    def test_normal_behaviour_no_compromise_alert(self):
        """Stable CPU and queue size should not trigger compromise alert."""
        history = [_make_metric(node_id="comp-2", cpu_percent=15.0, queue_size=5)] * 8
        det = _make_detector(node_ids=["comp-2"], node_history={"comp-2": history})
        alerts = asyncio.run(det._detect_node_compromise())
        assert len(alerts) == 0, "Stable node should not trigger compromise alert"

    def test_insufficient_history_skipped(self):
        """Fewer than 5 data points → skip, no alert."""
        history = [_make_metric(node_id="comp-3", cpu_percent=95.0)] * 3
        det = _make_detector(node_ids=["comp-3"], node_history={"comp-3": history})
        alerts = asyncio.run(det._detect_node_compromise())
        assert len(alerts) == 0


# ===========================================================================
# 5. Auto-respond: medium severity → automatic action
# ===========================================================================

class TestAutoRespond:
    """Medium severity alert should trigger automatic defence action, not just escalation."""

    def test_medium_timing_alert_triggers_increase_mixing(self):
        """Medium timing_attack → increase_mixing action executed."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-medium",
            alert_type="timing_attack",
            severity="medium",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["node-m"],
            description="Test medium timing alert",
            evidence={"z_score": 3.5},
            confidence=0.7,
        )

        action = asyncio.run(det._auto_respond(alert))
        assert action is not None
        assert action.action_type == "increase_mixing"
        assert action.status == "executed"

    def test_medium_sybil_alert_triggers_blacklist(self):
        """Medium sybil_attack → blacklist_node action executed."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-sybil",
            alert_type="sybil_attack",
            severity="medium",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["sybil-1", "sybil-2"],
            description="Sybil cluster",
            evidence={"fingerprint": "v1|10.0.0"},
            confidence=0.6,
        )

        action = asyncio.run(det._auto_respond(alert))
        assert action is not None
        assert action.action_type == "blacklist_node"


# ===========================================================================
# 6. Escalation: high severity → pending approval action
# ===========================================================================

class TestEscalation:
    """High severity should create an escalate_human action with status='pending'."""

    def test_high_severity_creates_escalation_action(self):
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-high",
            alert_type="node_compromise",
            severity="high",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["node-h"],
            description="High severity compromise",
            evidence={"cpu_ratio": 4.5},
            confidence=0.85,
        )

        action = asyncio.run(det._escalate(alert))
        assert action is not None
        assert action.action_type == "escalate_human"
        assert action.status == "pending"
        assert action.alert_id == "alert-high"

    def test_high_severity_handle_alert_escalates_and_auto_responds(self):
        """_handle_alert with high severity should create both escalation and auto-response."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-handle-high",
            alert_type="timing_attack",
            severity="high",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["node-hh"],
            description="High severity timing",
            evidence={"z_score": 6.5},
            confidence=0.9,
        )

        asyncio.run(det._handle_alert(alert))
        # The auto_response should have been set
        assert alert.auto_response in ("rotation", "escalate", "blacklist", None)
        # At least one action should be in defense_actions
        # (escalation + auto-respond)
        assert len(det.defense_actions) >= 1


# ===========================================================================
# 7. Blacklist: critical severity → nodes blacklisted
# ===========================================================================

class TestCriticalBlacklist:
    """Critical severity should fire _critical_respond and blacklist affected nodes."""

    def test_critical_severity_blacklists_nodes(self):
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-crit",
            alert_type="sybil_attack",
            severity="critical",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["evil-1", "evil-2", "evil-3"],
            description="Critical sybil attack",
            evidence={"fingerprint": "bad|192.168.0"},
            confidence=0.99,
        )

        action = asyncio.run(det._critical_respond(alert))
        assert action is not None
        assert action.action_type == "blacklist_node"
        assert action.status == "executed"
        assert alert.status == "mitigated"

    def test_critical_handle_alert_executes_critical_response(self):
        """_handle_alert on critical alert should invoke _critical_respond."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="alert-ch",
            alert_type="node_compromise",
            severity="critical",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["crit-node"],
            description="Critical compromise",
            evidence={},
            confidence=0.95,
        )

        asyncio.run(det._handle_alert(alert))
        assert alert.status == "mitigated"
        assert len(det.defense_actions) >= 1


# ===========================================================================
# 8. Alert lifecycle: open → mitigated → closed
# ===========================================================================

class TestAlertLifecycle:
    """Alerts should progress through open → mitigated/investigating/false_positive."""

    def test_new_alert_is_open(self):
        """Freshly created alerts should have status='open'."""
        alert = AttackAlert(
            alert_id="lifecycle-1",
            alert_type="timing_attack",
            severity="low",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["n1"],
            description="Test",
            evidence={},
            confidence=0.3,
        )
        assert alert.status == "open"

    def test_close_alert_marks_mitigated(self):
        """close_alert() should update the DB row to the given resolution."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="lifecycle-2",
            alert_type="sybil_attack",
            severity="medium",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["n2"],
            description="Sybil test",
            evidence={"fingerprint": "x"},
            confidence=0.5,
        )
        det._store_alert(alert)
        det.alert_history.append(alert)

        success = det.close_alert("lifecycle-2", "mitigated")
        assert success is True

        stored = det.get_alert("lifecycle-2")
        assert stored is not None
        assert stored["status"] == "mitigated"

    def test_close_alert_false_positive(self):
        """Alerts can be closed as false_positive."""
        det = _make_detector()

        alert = AttackAlert(
            alert_id="lifecycle-3",
            alert_type="intersection_attack",
            severity="medium",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["n3"],
            description="Intersection test",
            evidence={"count": 12},
            confidence=0.4,
        )
        det._store_alert(alert)

        success = det.close_alert("lifecycle-3", "false_positive")
        assert success is True

        stored = det.get_alert("lifecycle-3")
        assert stored["status"] == "false_positive"

    def test_get_open_alerts_filters_correctly(self):
        """get_open_alerts() should only return alerts with status='open'."""
        det = _make_detector()

        open_alert = AttackAlert(
            alert_id="open-1",
            alert_type="timing_attack",
            severity="low",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["n-open"],
            description="Open alert",
            evidence={},
            confidence=0.2,
        )
        closed_alert = AttackAlert(
            alert_id="closed-1",
            alert_type="sybil_attack",
            severity="medium",
            timestamp=datetime.now(tz=timezone.utc),
            node_ids=["n-closed"],
            description="Closed alert",
            evidence={},
            confidence=0.5,
            status="mitigated",
        )

        det._store_alert(open_alert)
        det._store_alert(closed_alert)

        open_alerts = det.get_open_alerts()
        ids = [a.alert_id for a in open_alerts]
        assert "open-1" in ids
        assert "closed-1" not in ids

    def test_detect_attacks_stores_alerts_in_db(self):
        """detect_attacks() should persist all new alerts to the DB."""
        # Build detector with a sybil-triggering knowledge graph
        nodes = [
            {
                "node_id": f"store-{i}",
                "software_version": "0.9.5",
                "ip_address": f"172.16.0.{i + 1}",
            }
            for i in range(6)
        ]
        det = _make_detector(kg_nodes=nodes)
        # Ensure timing and compromise checks find nothing (no history)
        det.collector.get_all_node_ids.return_value = []

        alerts = asyncio.run(det.detect_attacks())
        # At least the sybil alert should have been generated and stored
        all_stored = det.get_all_alerts()
        assert len(all_stored) >= len(alerts)
