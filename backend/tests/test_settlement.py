"""
JULIUS — Settlement Engine Tests
Covers: transaction logging, batch processing, revenue aggregation,
        payout preparation, and mark-paid.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from datetime import datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    """
    Provide a fresh SettlementEngine backed by a temporary SQLite DB.
    Patches VEIL_SETTLEMENT_MIN_PAYOUT to $0.00 so payouts are never
    blocked by the minimum threshold during tests.
    """
    # Patch config constants used inside the engine
    import backend.config as cfg  # noqa: E402

    monkeypatch.setattr(cfg, "VEIL_SETTLEMENT_MIN_PAYOUT", 0.0, raising=False)
    monkeypatch.setattr(cfg, "VEIL_SETTLEMENT_COMMISSION_RATE", 0.001, raising=False)

    db_file = str(tmp_path / "test_settlement.db")

    # Import after patching so module-level config reads pick up the monkeypatched values
    from backend.guardian.settlement import SettlementEngine

    eng = SettlementEngine(db_path=db_file)
    return eng


# ---------------------------------------------------------------------------
# 1. log_transaction — stored correctly
# ---------------------------------------------------------------------------


def test_log_transaction_stored(engine):
    """Logged transaction should appear in the transactions table."""
    serial_hash = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    tx_id = engine.log_transaction(
        node_id="node-001",
        token_serial_hash=serial_hash,
        bytes_routed=1024,
        commission=0.001024,
        partner_id="partner-A",
        source_entity="client-X",
        destination_entity="exit-Y",
    )

    assert tx_id, "Should return a non-empty transaction ID"

    result = engine.list_transactions(page=1, page_size=10)
    txns = result["transactions"]
    assert len(txns) == 1
    row = txns[0]

    assert row["id"] == tx_id
    assert row["node_id"] == "node-001"
    assert row["partner_id"] == "partner-A"
    assert row["token_serial_hash"] == serial_hash
    assert row["bytes_routed"] == 1024
    assert abs(row["commission_earned"] - 0.001024) < 1e-9
    assert row["source_entity"] == "client-X"
    assert row["destination_entity"] == "exit-Y"
    assert row["settled"] == 0, "Transaction should NOT be settled yet"


# ---------------------------------------------------------------------------
# 2. process_batch — groups by node, calculates totals, applies revenue share
# ---------------------------------------------------------------------------


def test_process_batch_grouping_and_totals(engine):
    """
    Batch must correctly group transactions, sum bytes/commission,
    and calculate the 30 % partner payout.
    """
    # Log 3 transactions for node-A and 2 for node-B
    for i in range(3):
        engine.log_transaction(
            node_id="node-A",
            token_serial_hash=f"hash-A-{i}",
            bytes_routed=1000,
            commission=0.001,
        )
    for i in range(2):
        engine.log_transaction(
            node_id="node-B",
            token_serial_hash=f"hash-B-{i}",
            bytes_routed=2000,
            commission=0.002,
        )

    batch = engine.process_batch()

    assert batch.total_transactions == 5
    assert batch.total_bytes == 3 * 1000 + 2 * 2000  # 7000
    assert abs(batch.total_commission - (3 * 0.001 + 2 * 0.002)) < 1e-9  # 0.007

    # Node-A summary
    a = batch.per_node_summary["node-A"]
    assert a.total_bytes == 3000
    assert abs(a.total_commission - 0.003) < 1e-9
    assert a.revenue_share_pct == 30.0
    assert abs(a.payout_amount - 0.003 * 0.30) < 1e-9

    # Node-B summary
    b = batch.per_node_summary["node-B"]
    assert b.total_bytes == 4000
    assert abs(b.total_commission - 0.004) < 1e-9
    assert abs(b.payout_amount - 0.004 * 0.30) < 1e-9


def test_process_batch_marks_transactions_settled(engine):
    """After processing, transactions must be flagged as settled."""
    engine.log_transaction("node-X", "hash-X", 512, 0.0005)
    engine.log_transaction("node-X", "hash-Y", 512, 0.0005)

    batch = engine.process_batch()

    # All should now be settled
    result = engine.list_transactions()
    for tx in result["transactions"]:
        assert tx["settled"] == 1, f"TX {tx['id']} should be settled"
        assert tx["batch_id"] == batch.batch_id

    # A second batch with no new transactions should be empty
    batch2 = engine.process_batch()
    assert batch2.total_transactions == 0


# ---------------------------------------------------------------------------
# 3. Revenue aggregation — correct totals by time range
# ---------------------------------------------------------------------------


def test_revenue_aggregation_totals(engine):
    """get_revenue should sum all transactions and return per-node breakdown."""
    # Log 5 transactions across 2 nodes
    for _ in range(3):
        engine.log_transaction("node-R1", "h1", 1024, 0.001)
    for _ in range(2):
        engine.log_transaction("node-R2", "h2", 2048, 0.002)

    rev = engine.get_revenue()

    expected_total = 3 * 0.001 + 2 * 0.002  # 0.007
    assert abs(rev.total_revenue - expected_total) < 1e-9

    node_ids = {n.node_id for n in rev.per_node_revenue}
    assert "node-R1" in node_ids
    assert "node-R2" in node_ids

    r1 = next(n for n in rev.per_node_revenue if n.node_id == "node-R1")
    assert r1.transaction_count == 3
    assert abs(r1.total_commission - 0.003) < 1e-9
    assert abs(r1.payout_amount - 0.003 * 0.30) < 1e-9


def test_revenue_empty_db(engine):
    """get_revenue on an empty DB should return zeros without raising."""
    rev = engine.get_revenue()
    assert rev.total_revenue == 0.0
    assert rev.revenue_today == 0.0
    assert rev.per_node_revenue == []
    assert rev.revenue_trend == []


# ---------------------------------------------------------------------------
# 4. Payout preparation — correct instruction format
# ---------------------------------------------------------------------------


def test_prepare_payout_format(engine):
    """prepare_payout should return a correctly structured instruction dict."""
    # Seed a node record via batch processing
    engine.log_transaction("node-P1", "hash-P", 4096, 0.004, partner_id="partner-Z")
    engine.process_batch()

    instruction = engine.prepare_payout(node_id="node-P1", amount=1.50)

    assert "payout_id" in instruction
    assert instruction["node_id"] == "node-P1"
    assert instruction["partner_id"] == "partner-Z"
    assert abs(instruction["amount_usd"] - 1.50) < 1e-9
    assert instruction["currency"] == "USD"
    assert instruction["status"] == "prepared"
    assert "prepared_at" in instruction


def test_prepare_payout_below_minimum(engine, monkeypatch):
    """prepare_payout should reject amounts below the configured minimum."""
    import backend.config as cfg

    monkeypatch.setattr(cfg, "VEIL_SETTLEMENT_MIN_PAYOUT", 5.0, raising=False)

    result = engine.prepare_payout(node_id="node-Q", amount=0.50)
    assert result.get("error") == "below_minimum"
    assert result["minimum_usd"] == 5.0


# ---------------------------------------------------------------------------
# 5. mark_paid — status update
# ---------------------------------------------------------------------------


def test_mark_paid_updates_status(engine):
    """mark_paid should update the node record status to 'paid' and return True."""
    engine.log_transaction("node-M", "hash-M", 8192, 0.008)
    batch = engine.process_batch()

    # Fetch the node record ID from the DB directly
    import sqlite3

    with sqlite3.connect(engine.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, status FROM settlement_node_records WHERE node_id='node-M'"
        ).fetchone()

    assert row is not None
    assert row["status"] == "pending"  # or "below_minimum" at 0 min

    updated = engine.mark_paid(row["id"])
    assert updated is True

    # Verify in DB
    with sqlite3.connect(engine.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row2 = conn.execute(
            "SELECT status FROM settlement_node_records WHERE id=?", (row["id"],)
        ).fetchone()
    assert row2["status"] == "paid"


def test_mark_paid_nonexistent_returns_false(engine):
    """mark_paid with an unknown ID should return False without raising."""
    result = engine.mark_paid("does-not-exist-at-all")
    assert result is False


# ---------------------------------------------------------------------------
# 6. list_batches and pagination
# ---------------------------------------------------------------------------


def test_list_batches_returns_records(engine):
    """list_batches should return all processed batch headers."""
    engine.log_transaction("node-L", "hash-L1", 100, 0.0001)
    engine.process_batch()
    engine.log_transaction("node-L", "hash-L2", 200, 0.0002)
    engine.process_batch()

    batches = engine.list_batches(limit=10)
    assert len(batches) == 2
    assert all("batch_id" in b for b in batches)


def test_list_transactions_pagination(engine):
    """list_transactions should honour page / page_size params."""
    for i in range(15):
        engine.log_transaction("node-PAG", f"hash-{i}", 100, 0.0001)

    page1 = engine.list_transactions(page=1, page_size=10)
    assert len(page1["transactions"]) == 10
    assert page1["total"] == 15
    assert page1["pages"] == 2

    page2 = engine.list_transactions(page=2, page_size=10)
    assert len(page2["transactions"]) == 5
