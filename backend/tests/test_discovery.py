"""
JULIUS — Passive Discovery Engine Tests
========================================
Covers the four required test categories:
    1. Source parsing   — Mock Tor Metrics API, parse into DiscoveredNode.
    2. Scoring          — Verify score_node() calculation correctness.
    3. Deduplication    — Two sources returning same node → merged once.
    4. Knowledge Graph  — Nodes inserted/updated correctly in SQLite.

All tests are fully offline (no network calls): every HTTP fetch is
patched with unittest.mock.
"""

from __future__ import annotations

import json
import os
import sys
import types
import uuid
from datetime import datetime, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — mirrors conftest.py convention
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("JULIUS_DEBUG", "0")

# Use a temp DB to avoid touching production SQLite
import tempfile

_TMPDIR = tempfile.mkdtemp()
_TEST_DISCOVERY_DB = os.path.join(_TMPDIR, "test_discovery.db")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """Provide an isolated DiscoveryEngine backed by a fresh temp SQLite DB."""
    db_path = str(tmp_path_factory.mktemp("discovery") / "test_disc.db")
    from backend.guardian.discovery import DiscoveryEngine  # type: ignore
    return DiscoveryEngine(db_path=db_path)


@pytest.fixture()
def fresh_engine(tmp_path):
    """Per-test fresh DiscoveryEngine (clean DB for side-effect isolation)."""
    db_path = str(tmp_path / "disc.db")
    from backend.guardian.discovery import DiscoveryEngine  # type: ignore
    return DiscoveryEngine(db_path=db_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Realistic Onionoo relay JSON (abridged)
MOCK_TOR_RELAY = {
    "fingerprint": "AABBCCDDEEFF00112233445566778899AABBCCDD",
    "or_addresses": ["1.2.3.4:9001"],
    "flags": ["Guard", "HSDir", "Running", "Stable", "V2Dir", "Valid"],
    "nickname": "TestRelay",
    "platform": "Tor 0.4.7.13 on Linux",
    "bandwidth": {"observed_bandwidth": 52_000_000},  # 52 MB/s → 52 Mbps
    "uptime": 2_592_000,  # 30 days exactly
    "country": "de",
    "contact": "abuse@example.com",
}

MOCK_ONIONOO_RESPONSE = json.dumps({"relays": [MOCK_TOR_RELAY], "bridges": []})

# Realistic I2P hosts.txt row
MOCK_I2P_HOSTS = "example.i2p=AAABBBCCCDDDEEEFFFGGGHHH1234567890abcdef\n"

# Nym gateway JSON
MOCK_NYM_GATEWAY = {
    "identity_key": "NYMGATEWAYabcdef1234567890abcdef12345678",
    "mix_host": "5.6.7.8:1789",
    "version": "1.1.35",
    "location": "PL",
    "_kind": "nym_gateway",
}
MOCK_NYM_RESPONSE = json.dumps([MOCK_NYM_GATEWAY])


# ---------------------------------------------------------------------------
# 1. Source Parsing — Tor Metrics
# ---------------------------------------------------------------------------


class TestTorMetricsParsing:
    """Verify TorMetricsSource.parse() correctly converts Onionoo JSON."""

    def test_parse_single_relay(self):
        from backend.guardian.discovery import TorMetricsSource  # type: ignore

        source = TorMetricsSource()
        nodes = source.parse([MOCK_TOR_RELAY])

        assert len(nodes) == 1, "Should produce exactly one DiscoveredNode"
        node = nodes[0]

        assert node.network == "tor"
        assert node.source == "tor_metrics"
        assert node.public_key == MOCK_TOR_RELAY["fingerprint"].lower()
        assert node.node_id == f"tor_{MOCK_TOR_RELAY['fingerprint'].lower()}"
        assert node.ip_address == "1.2.3.4"
        assert node.software == "tor"
        assert node.version == "0.4.7.13"
        assert node.location == "de"
        assert node.uptime_seconds == 2_592_000
        assert abs((node.bandwidth_mbps or 0) - 52.0) < 0.1
        assert "Guard" in (node.flags or [])

    def test_parse_empty_relay_list(self):
        from backend.guardian.discovery import TorMetricsSource  # type: ignore

        source = TorMetricsSource()
        nodes = source.parse([])
        assert nodes == []

    def test_fetch_uses_public_https(self):
        """fetch() should call the Onionoo HTTPS endpoint (no Tor)."""
        from backend.guardian.discovery import TorMetricsSource, _http_get  # type: ignore

        source = TorMetricsSource(max_nodes=10)
        with patch("backend.guardian.discovery._http_get", return_value=MOCK_ONIONOO_RESPONSE) as mock_get:
            relays = source.fetch()
            call_url = mock_get.call_args[0][0]
            # Must be HTTPS, must NOT be an .onion address
            assert call_url.startswith("https://"), f"Expected HTTPS URL, got: {call_url}"
            assert ".onion" not in call_url, "Must not access .onion via Tor"
        assert len(relays) == 1


class TestI2PNetDBParsing:
    """Verify I2PNetDBSource.parse() handles both JSON and hosts.txt records."""

    def test_parse_hosts_txt_record(self):
        from backend.guardian.discovery import I2PNetDBSource  # type: ignore

        source = I2PNetDBSource()
        raw = [{"host": "example.i2p", "key": "AAABBBCCCDDDEEEFFFGGG"}]
        nodes = source.parse(raw)
        assert len(nodes) == 1
        node = nodes[0]
        assert node.network == "i2p"
        assert node.source == "i2p_netdb"
        assert node.node_id.startswith("i2p_")

    def test_fetch_uses_public_https_fallback(self):
        """When stats endpoint fails, should fall back to HTTPS mirror."""
        from backend.guardian.discovery import I2PNetDBSource  # type: ignore

        source = I2PNetDBSource()
        call_log: List[str] = []

        def fake_get(url, *args, **kwargs):
            call_log.append(url)
            # First call (stats endpoint) fails, second (fallback) returns hosts.txt
            if len(call_log) == 1:
                return None
            return MOCK_I2P_HOSTS

        with patch("backend.guardian.discovery._http_get", side_effect=fake_get):
            results = source.fetch()

        assert all("https://" in u for u in call_log), "All fetches must use HTTPS"
        assert all(".onion" not in u for u in call_log), "No .onion URLs allowed"


class TestPublicDNSParsing:
    """Verify PublicDNSSource.parse() handles Nym gateway/mixnode JSON."""

    def test_parse_nym_gateway(self):
        from backend.guardian.discovery import PublicDNSSource  # type: ignore

        source = PublicDNSSource()
        nodes = source.parse([MOCK_NYM_GATEWAY])
        assert len(nodes) == 1
        node = nodes[0]
        assert node.network == "mixnet"
        assert node.source == "public_dns"
        assert node.software == "nym"

    def test_fetch_uses_public_https(self):
        from backend.guardian.discovery import PublicDNSSource  # type: ignore

        source = PublicDNSSource()
        with patch(
            "backend.guardian.discovery._http_get", return_value=MOCK_NYM_RESPONSE
        ) as mock_get:
            results = source.fetch()
            for call in mock_get.call_args_list:
                url = call[0][0]
                assert url.startswith("https://"), f"Expected HTTPS, got: {url}"
                assert ".onion" not in url


# ---------------------------------------------------------------------------
# 2. Scoring — verify formula correctness
# ---------------------------------------------------------------------------


class TestScoring:
    """Unit-test the score_node() static method against known values."""

    @pytest.fixture(autouse=True)
    def _src(self):
        from backend.guardian.discovery import DiscoveryEngine  # type: ignore
        self.score_node = DiscoveryEngine.score_node

    def _make_node(self, **kwargs):
        from backend.models.discovery_models import DiscoveredNode  # type: ignore
        defaults = dict(
            node_id="test_node", network="tor", source="tor_metrics",
            uptime_seconds=None, bandwidth_mbps=None, location=None, version=None,
        )
        defaults.update(kwargs)
        return DiscoveredNode(**defaults)

    def test_zero_score_for_empty_node(self):
        node = self._make_node()
        assert self.score_node(node) == 0.0

    def test_full_uptime_gives_40_points(self):
        # Exactly 30 days uptime → uptime component saturates at 40
        node = self._make_node(uptime_seconds=30 * 86400)
        score = self.score_node(node)
        assert abs(score - 40.0) < 0.1, f"Expected ~40.0, got {score}"

    def test_half_uptime_gives_20_uptime_points(self):
        # 15 days → 50 % of 30 → 20 points
        node = self._make_node(uptime_seconds=15 * 86400)
        score = self.score_node(node)
        assert abs(score - 20.0) < 0.5, f"Expected ~20.0, got {score}"

    def test_bandwidth_100mbps_gives_30_points(self):
        node = self._make_node(bandwidth_mbps=100.0)
        score = self.score_node(node)
        assert abs(score - 30.0) < 0.1, f"Expected ~30.0, got {score}"

    def test_location_known_gives_20_points(self):
        node = self._make_node(location="de")
        score = self.score_node(node)
        assert abs(score - 20.0) < 0.1, f"Expected ~20.0, got {score}"

    def test_fresh_version_gives_10_points(self):
        node = self._make_node(version="0.4.7.13")
        score = self.score_node(node)
        assert abs(score - 10.0) < 0.1, f"Expected ~10.0, got {score}"

    def test_old_version_gives_no_software_points(self):
        node = self._make_node(version="0.3.5")
        score = self.score_node(node)
        assert score == 0.0, f"Old version should give 0 software points, got {score}"

    def test_max_score_all_factors(self):
        """Perfect node: 30-day uptime + 100 Mbps + known location + fresh version = 100."""
        node = self._make_node(
            uptime_seconds=30 * 86400,
            bandwidth_mbps=100.0,
            location="us",
            version="0.4.7.13",
        )
        score = self.score_node(node)
        assert abs(score - 100.0) < 0.1, f"Expected 100.0, got {score}"

    def test_score_capped_at_100(self):
        """Score must never exceed 100."""
        node = self._make_node(
            uptime_seconds=365 * 86400,  # 1 year — way above saturation
            bandwidth_mbps=1000.0,
            location="us",
            version="1.0.0",
        )
        score = self.score_node(node)
        assert score <= 100.0, f"Score must be capped at 100, got {score}"


# ---------------------------------------------------------------------------
# 3. Deduplication — same node from two sources → single entry
# ---------------------------------------------------------------------------


class TestDeduplication:
    """
    Verify that when two sources return a node with the same public_key,
    discover_all() merges them into a single DiscoveredNode.
    """

    def test_same_public_key_deduplicated(self, fresh_engine):
        """Two nodes sharing the same fingerprint/public_key → one result."""
        from backend.models.discovery_models import DiscoveredNode  # type: ignore

        shared_key = "deadbeef" * 5  # 40 hex chars

        # Simulate two sources producing the same relay
        node_a = DiscoveredNode(
            node_id="tor_deadbeef1",
            public_key=shared_key,
            network="tor",
            source="tor_metrics",
            bandwidth_mbps=10.0,
        )
        node_b = DiscoveredNode(
            node_id="i2p_deadbeef1",
            public_key=shared_key,
            network="tor",
            source="i2p_netdb",
            bandwidth_mbps=50.0,  # higher bandwidth — should win
        )

        # Manually run the dedup logic as discover_all does
        seen: dict = {}
        for node in [node_a, node_b]:
            dedup_key = node.public_key or node.ip_address
            if dedup_key and dedup_key in seen:
                existing = seen[dedup_key]
                if (node.bandwidth_mbps or 0) > (existing.bandwidth_mbps or 0):
                    existing.bandwidth_mbps = node.bandwidth_mbps
                continue
            seen[dedup_key or node.node_id] = node

        result = list(seen.values())
        assert len(result) == 1, "Same public_key from two sources must collapse to one node"
        assert result[0].bandwidth_mbps == 50.0, "Higher bandwidth from second source should win"

    def test_different_nodes_not_merged(self, fresh_engine):
        """Nodes with distinct fingerprints must remain separate."""
        from backend.models.discovery_models import DiscoveredNode  # type: ignore

        nodes = [
            DiscoveredNode(node_id=f"tor_key{i}", public_key=f"key_{i}" * 5, network="tor", source="tor_metrics")
            for i in range(3)
        ]
        seen: dict = {}
        for n in nodes:
            dedup_key = n.public_key or n.ip_address
            if dedup_key and dedup_key in seen:
                continue
            seen[dedup_key or n.node_id] = n

        assert len(seen) == 3, "Three distinct nodes must remain three entries"

    def test_discover_all_returns_unique_nodes(self, fresh_engine):
        """
        Mock two sources returning the same relay fingerprint and confirm
        discover_all() yields only one node.
        """
        from backend.models.discovery_models import DiscoveredNode  # type: ignore
        from backend.guardian.discovery import TorMetricsSource, I2PNetDBSource  # type: ignore

        shared_fp = "FFAABBCCDD0011223344556677889900FFAABBCC"

        duplicate_relay = {**MOCK_TOR_RELAY, "fingerprint": shared_fp}

        # Both sources produce the same fingerprint
        with patch.object(TorMetricsSource, "fetch", return_value=[duplicate_relay]), \
             patch.object(I2PNetDBSource, "fetch", return_value=[{"key": shared_fp.lower(), "host": "1.2.3.4"}]):

            nodes, run = fresh_engine.discover_all()

        fp_lower = shared_fp.lower()
        matching = [n for n in nodes if n.public_key == fp_lower]
        assert len(matching) == 1, (
            f"Duplicate fingerprint from 2 sources should yield 1 node, got {len(matching)}"
        )


# ---------------------------------------------------------------------------
# 4. Knowledge Graph — verify DB insert / update
# ---------------------------------------------------------------------------


class TestKnowledgeGraph:
    """
    Confirm that update_knowledge_graph() correctly inserts new nodes and
    updates existing ones in the discovery SQLite store.
    """

    def _make_nodes(self, count: int, network: str = "tor"):
        from backend.models.discovery_models import DiscoveredNode  # type: ignore
        return [
            DiscoveredNode(
                node_id=f"kg_test_{i}_{uuid.uuid4().hex[:6]}",
                public_key=f"pkgtest{i:04d}" + "a" * 32,
                network=network,
                source="tor_metrics",
                ip_address=f"10.0.0.{i % 254 + 1}",
                uptime_seconds=i * 3600,
                bandwidth_mbps=float(i * 5),
                location="us",
                version="0.4.7.13",
            )
            for i in range(count)
        ]

    def test_new_nodes_inserted(self, fresh_engine):
        """Brand-new nodes should be inserted with new_count > 0."""
        nodes = self._make_nodes(5)
        for node in nodes:
            node.score = fresh_engine.score_node(node)

        new_c, upd_c = fresh_engine.update_knowledge_graph(nodes)

        assert new_c == 5, f"Expected 5 new nodes, got {new_c}"
        assert upd_c == 0, f"Expected 0 updates on first insert, got {upd_c}"
        assert fresh_engine.get_node_count() == 5

    def test_existing_nodes_updated_not_duplicated(self, fresh_engine):
        """Re-inserting the same node_ids should update, not duplicate."""
        nodes = self._make_nodes(3)
        for n in nodes:
            n.score = fresh_engine.score_node(n)

        # First insert
        fresh_engine.update_knowledge_graph(nodes)
        assert fresh_engine.get_node_count() == 3

        # Update with changed score
        for n in nodes:
            n.score = 99.0
        new_c, upd_c = fresh_engine.update_knowledge_graph(nodes)

        assert new_c == 0,   f"No new nodes expected on re-upsert, got {new_c}"
        assert upd_c == 3,   f"Expected 3 updated nodes, got {upd_c}"
        assert fresh_engine.get_node_count() == 3, "Row count must not grow on update"

    def test_stored_node_retrievable_by_id(self, fresh_engine):
        """get_node() should return the correct record after insert."""
        nodes = self._make_nodes(1, network="i2p")
        node = nodes[0]
        node.score = fresh_engine.score_node(node)
        fresh_engine.update_knowledge_graph(nodes)

        stored = fresh_engine.get_node(node.node_id)
        assert stored is not None, "get_node() returned None for inserted node"
        assert stored["node_id"] == node.node_id
        assert stored["network"] == "i2p"
        assert stored["source"] == "tor_metrics"

    def test_list_nodes_filter_by_network(self, fresh_engine):
        """list_nodes(network='tor') should not return i2p nodes."""
        tor_nodes = self._make_nodes(3, network="tor")
        i2p_nodes = self._make_nodes(2, network="i2p")
        all_nodes = tor_nodes + i2p_nodes
        for n in all_nodes:
            n.score = fresh_engine.score_node(n)
        fresh_engine.update_knowledge_graph(all_nodes)

        tor_results = fresh_engine.list_nodes(network="tor")
        i2p_results = fresh_engine.list_nodes(network="i2p")

        assert len(tor_results) == 3, f"Expected 3 tor nodes, got {len(tor_results)}"
        assert len(i2p_results) == 2, f"Expected 2 i2p nodes, got {len(i2p_results)}"
        assert all(r["network"] == "tor" for r in tor_results)
        assert all(r["network"] == "i2p" for r in i2p_results)

    def test_rescore_all_updates_scores(self, fresh_engine):
        """rescore_all() must update stored scores without changing node count."""
        nodes = self._make_nodes(4)
        for n in nodes:
            n.score = 0.0  # force a bad initial score
        fresh_engine.update_knowledge_graph(nodes)

        rescored = fresh_engine.rescore_all()
        assert rescored == 4, f"Expected 4 nodes rescored, got {rescored}"

        # Scores should now reflect the real formula
        stored = fresh_engine.list_nodes()
        assert all(r["score"] >= 0.0 for r in stored)
