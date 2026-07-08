"""
JULIUS — Revenue API Tests
Tests for the four revenue dashboard endpoints:
  1. /guardian/revenue/summary  — correct totals
  2. /guardian/revenue/trend    — 30-day series
  3. /guardian/revenue/nodes    — per-node breakdown
  4. /guardian/transactions     — pagination

Strategy: instantiate SettlementEngine directly with a tmp_path SQLite file
so tests are fully isolated and do not require a running HTTP server or auth.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    """
    Provide a fresh SettlementEngine backed by a temporary SQLite DB.
    Monkeypatches config constants so payouts are never blocked by the
    minimum threshold during testing.
    """
    import backend.config as cfg

    monkeypatch.setattr(cfg, "VEIL_SETTLEMENT_MIN_PAYOUT", 0.0, raising=False)
    monkeypatch.setattr(cfg, "VEIL_SETTLEMENT_COMMISSION_RATE", 0.001, raising=False)

    db_file = str(tmp_path / "test_revenue_api.db")

    from backend.guardian.settlement import SettlementEngine

    return SettlementEngine(db_path=db_file)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _seed_transactions(engine, *, nodes: dict, settled: bool = False) -> None:
    """
    Seed transactions from a mapping of {node_id: [(bytes, commission), ...]}.
    Optionally run a settlement batch to mark them settled.
    """
    for node_id, records in nodes.items():
        for i, (byt, comm) in enumerate(records):
            engine.log_transaction(
                node_id=node_id,
                token_serial_hash=f"hash-{node_id}-{i}",
                bytes_routed=byt,
                commission=comm,
                partner_id=f"partner-{node_id}",
            )
    if settled:
        engine.process_batch()


# ===========================================================================
# Test 1 — Summary endpoint returns correct totals
# ===========================================================================


def test_revenue_summary_correct_totals(engine):
    """
    get_revenue() (backing /guardian/revenue/summary) must return accurate
    all-time totals and per-period breakdowns.
    """
    # Seed 3 txns for node-A, 2 for node-B
    _seed_transactions(
        engine,
        nodes={
            "node-A": [(1000, 0.001), (2000, 0.002), (3000, 0.003)],
            "node-B": [(4000, 0.004), (5000, 0.005)],
        },
    )

    rev = engine.get_revenue()

    expected_total = 3 * 0.001 + 0.002 + 0.003 + 0.004 + 0.005
    # Recalculate precisely
    expected_total = 0.001 + 0.002 + 0.003 + 0.004 + 0.005

    assert abs(rev.total_revenue - expected_total) < 1e-9, (
        f"total_revenue mismatch: got {rev.total_revenue}, expected {expected_total}"
    )

    # Since all transactions are inserted right now, all fall in today/week/month
    assert abs(rev.revenue_today - expected_total) < 1e-9, (
        "revenue_today should equal total_revenue for freshly inserted transactions"
    )
    assert abs(rev.revenue_this_week - expected_total) < 1e-9
    assert abs(rev.revenue_this_month - expected_total) < 1e-9

    # Validate derived RevenueSummary fields
    from backend.models.revenue_models import RevenueSummary

    if rev.revenue_trend:
        avg_daily = sum(d.total_commission for d in rev.revenue_trend) / len(
            rev.revenue_trend
        )
    else:
        avg_daily = 0.0

    active_nodes = sum(1 for n in rev.per_node_revenue if n.total_commission > 0)

    summary = RevenueSummary(
        total_revenue=rev.total_revenue,
        revenue_today=rev.revenue_today,
        revenue_this_week=rev.revenue_this_week,
        revenue_this_month=rev.revenue_this_month,
        average_daily_revenue=round(avg_daily, 6),
        node_count=len(rev.per_node_revenue),
        active_nodes=active_nodes,
    )

    assert summary.node_count == 2
    assert summary.active_nodes == 2
    assert abs(summary.total_revenue - expected_total) < 1e-9


# ===========================================================================
# Test 2 — Trend endpoint returns 30 days of data
# ===========================================================================


def test_revenue_trend_30_days(engine, monkeypatch):
    """
    get_revenue().revenue_trend must cover the last 30 calendar days.
    We inject one transaction per day for 30 days by patching the
    timestamp directly in the SQLite DB.
    """
    import sqlite3

    # Insert one transaction per day for the last 30 days
    now = datetime.now(timezone.utc)
    for i in range(30):
        day = now - timedelta(days=i)
        tx_id = engine.log_transaction(
            node_id="node-trend",
            token_serial_hash=f"hash-trend-{i}",
            bytes_routed=1000,
            commission=0.001,
        )
        # Back-date the timestamp so it falls on day i
        ts_str = day.replace(hour=12, minute=0, second=0, microsecond=0).isoformat()
        with sqlite3.connect(engine.db_path) as conn:
            conn.execute(
                "UPDATE settlement_transactions SET timestamp=? WHERE id=?",
                (ts_str, tx_id),
            )

    rev = engine.get_revenue()
    trend = rev.revenue_trend

    assert len(trend) == 30, (
        f"Expected 30 trend points, got {len(trend)}"
    )

    # Every day should have exactly 1 transaction and $0.001 commission
    for point in trend:
        assert point.transaction_count == 1
        assert abs(point.total_commission - 0.001) < 1e-9

    # Validate RevenueTrendPoint model mapping
    from backend.models.revenue_models import RevenueTrendPoint

    typed_trend = [
        RevenueTrendPoint(
            date=d.date,
            revenue=d.total_commission,
            transactions=d.transaction_count,
        )
        for d in trend
    ]
    assert len(typed_trend) == 30
    # Dates must be YYYY-MM-DD strings
    for pt in typed_trend:
        assert len(pt.date) == 10
        assert pt.date[4] == "-" and pt.date[7] == "-"


# ===========================================================================
# Test 3 — Nodes endpoint returns per-node breakdown
# ===========================================================================


def test_revenue_nodes_per_node_breakdown(engine):
    """
    get_revenue().per_node_revenue must contain one entry per node
    with correct aggregated bytes, commission, and payout_amount.
    """
    _seed_transactions(
        engine,
        nodes={
            "node-X": [(1024, 0.001024)] * 4,   # 4 txns, 4096 bytes, $0.004096 total
            "node-Y": [(2048, 0.002048)] * 2,   # 2 txns, 4096 bytes, $0.004096 total
            "node-Z": [(512, 0.000512)],        # 1 txn,   512 bytes, $0.000512 total
        },
    )

    rev = engine.get_revenue()
    nodes_map = {n.node_id: n for n in rev.per_node_revenue}

    assert "node-X" in nodes_map
    assert "node-Y" in nodes_map
    assert "node-Z" in nodes_map

    nx = nodes_map["node-X"]
    assert nx.total_bytes == 4 * 1024
    assert abs(nx.total_commission - 4 * 0.001024) < 1e-9
    expected_payout_x = nx.total_commission * 0.30
    assert abs(nx.payout_amount - expected_payout_x) < 1e-9
    assert nx.transaction_count == 4

    ny = nodes_map["node-Y"]
    assert ny.total_bytes == 2 * 2048
    assert abs(ny.total_commission - 2 * 0.002048) < 1e-9
    assert ny.transaction_count == 2

    nz = nodes_map["node-Z"]
    assert nz.total_bytes == 512
    assert abs(nz.total_commission - 0.000512) < 1e-9
    assert nz.transaction_count == 1

    # Validate NodeRevenue model round-trip
    from backend.models.revenue_models import NodeRevenue

    typed_nodes = [
        NodeRevenue(
            node_id=n.node_id,
            partner_id=n.partner_id,
            total_bytes=n.total_bytes,
            total_commission=n.total_commission,
            revenue_share_pct=30.0,
            payout_amount=n.payout_amount,
        )
        for n in rev.per_node_revenue
    ]
    assert len(typed_nodes) == 3
    for tn in typed_nodes:
        assert tn.revenue_share_pct == 30.0
        assert tn.payout_amount >= 0.0


# ===========================================================================
# Test 4 — Transactions endpoint paginates correctly
# ===========================================================================


def test_transactions_pagination(engine):
    """
    list_transactions must honour page / page_size and return correct
    total, pages, and per-page counts.
    """
    # Insert 25 transactions
    for i in range(25):
        engine.log_transaction(
            node_id="node-page",
            token_serial_hash=f"hash-page-{i}",
            bytes_routed=100,
            commission=0.0001,
        )

    # Page 1 of 3 (page_size=10)
    p1 = engine.list_transactions(page=1, page_size=10)
    assert p1["total"] == 25
    assert p1["pages"] == 3
    assert len(p1["transactions"]) == 10
    assert p1["page"] == 1
    assert p1["page_size"] == 10

    # Page 2
    p2 = engine.list_transactions(page=2, page_size=10)
    assert len(p2["transactions"]) == 10

    # Page 3 — only 5 remaining
    p3 = engine.list_transactions(page=3, page_size=10)
    assert len(p3["transactions"]) == 5

    # Page 4 — beyond last page, should return empty list
    p4 = engine.list_transactions(page=4, page_size=10)
    assert len(p4["transactions"]) == 0

    # Filter by node_id
    pf = engine.list_transactions(page=1, page_size=50, node_id="node-page")
    assert pf["total"] == 25

    # Filter by unknown node_id — should return zero rows
    pz = engine.list_transactions(page=1, page_size=10, node_id="does-not-exist")
    assert pz["total"] == 0
    assert len(pz["transactions"]) == 0
