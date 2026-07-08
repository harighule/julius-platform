"""
JULIUS — Guardian Settlement Engine
Tracks all token usage, calculates commissions, generates settlement batches,
and prepares payout instructions for node operators.

Database layout (SQLite)
------------------------
    settlement_transactions  — every routed packet with billing metadata
    settlement_batches       — processed batch header records
    settlement_node_records  — per-node summary rows linked to a batch
    settlement_payouts       — payout instructions emitted to operators
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..models.settlement_models import (
    DailyRevenue,
    NodeRevenue,
    NodeSettlement,
    PayoutInstruction,
    RevenueResponse,
    SettlementBatch,
    Transaction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Settlement Engine
# ---------------------------------------------------------------------------

class SettlementEngine:
    """
    Core settlement engine for VEIL Protocol bandwidth billing.

    Usage
    -----
    Call ``log_transaction`` for every successfully routed packet.
    The hourly background task (registered in main.py) calls
    ``process_batch`` to aggregate pending rows into a batch and
    mark them settled.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            os.makedirs(_db_dir, exist_ok=True)
            db_path = os.path.join(_db_dir, "settlement.db")
        self.db_path = db_path
        self._last_batch_time: datetime = _utcnow()
        self._init_db()
        logger.info("SettlementEngine initialised — db=%s", self.db_path)

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create all settlement tables if they do not already exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settlement_transactions (
                    id                  TEXT PRIMARY KEY,
                    timestamp           TEXT NOT NULL,
                    node_id             TEXT NOT NULL,
                    partner_id          TEXT,
                    token_serial_hash   TEXT NOT NULL,
                    bytes_routed        INTEGER NOT NULL DEFAULT 0,
                    commission_earned   REAL NOT NULL DEFAULT 0.0,
                    source_entity       TEXT,
                    destination_entity  TEXT,
                    settled             INTEGER NOT NULL DEFAULT 0,
                    batch_id            TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_tx_settled
                    ON settlement_transactions (settled, timestamp);
                CREATE INDEX IF NOT EXISTS idx_tx_node
                    ON settlement_transactions (node_id);

                CREATE TABLE IF NOT EXISTS settlement_batches (
                    batch_id            TEXT PRIMARY KEY,
                    start_time          TEXT NOT NULL,
                    end_time            TEXT NOT NULL,
                    total_transactions  INTEGER NOT NULL DEFAULT 0,
                    total_bytes         INTEGER NOT NULL DEFAULT 0,
                    total_commission    REAL NOT NULL DEFAULT 0.0,
                    created_at          TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settlement_node_records (
                    id                  TEXT PRIMARY KEY,
                    batch_id            TEXT NOT NULL,
                    node_id             TEXT NOT NULL,
                    partner_id          TEXT,
                    total_bytes         INTEGER NOT NULL DEFAULT 0,
                    total_commission    REAL NOT NULL DEFAULT 0.0,
                    revenue_share_pct   REAL NOT NULL DEFAULT 30.0,
                    payout_amount       REAL NOT NULL DEFAULT 0.0,
                    status              TEXT NOT NULL DEFAULT 'pending',
                    FOREIGN KEY (batch_id) REFERENCES settlement_batches(batch_id)
                );

                CREATE TABLE IF NOT EXISTS settlement_payouts (
                    payout_id           TEXT PRIMARY KEY,
                    node_id             TEXT NOT NULL,
                    partner_id          TEXT,
                    amount_usd          REAL NOT NULL DEFAULT 0.0,
                    currency            TEXT NOT NULL DEFAULT 'USD',
                    prepared_at         TEXT NOT NULL,
                    status              TEXT NOT NULL DEFAULT 'prepared',
                    memo                TEXT
                );
                """
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_transaction(
        self,
        node_id: str,
        token_serial_hash: str,
        bytes_routed: int,
        commission: float,
        partner_id: Optional[str] = None,
        source_entity: Optional[str] = None,
        destination_entity: Optional[str] = None,
    ) -> str:
        """
        Store a single packet-routing billing event.

        Returns the transaction ID.
        """
        tx_id = str(uuid.uuid4())
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO settlement_transactions
                    (id, timestamp, node_id, partner_id, token_serial_hash,
                     bytes_routed, commission_earned, source_entity,
                     destination_entity, settled)
                VALUES (?,?,?,?,?,?,?,?,?,0)
                """,
                (
                    tx_id,
                    _iso(now),
                    node_id,
                    partner_id,
                    token_serial_hash,
                    bytes_routed,
                    commission,
                    source_entity,
                    destination_entity,
                ),
            )
        logger.debug(
            "TX logged | id=%s node=%s bytes=%d commission=%.6f",
            tx_id, node_id, bytes_routed, commission,
        )
        return tx_id

    def process_batch(self) -> SettlementBatch:
        """
        Aggregate all pending (unsettled) transactions into a settlement batch.

        Steps
        -----
        1. Fetch all unsettled transactions.
        2. Group by node_id, calculate bytes + commission totals.
        3. Apply revenue share (30 % → partner payout).
        4. Insert batch header + per-node records.
        5. Mark transactions as settled.
        6. Return the SettlementBatch object.
        """
        from ..config import VEIL_SETTLEMENT_MIN_PAYOUT  # noqa: lazy import

        batch_id = str(uuid.uuid4())
        batch_start = self._last_batch_time
        batch_end = _utcnow()
        self._last_batch_time = batch_end

        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM settlement_transactions WHERE settled = 0"
            ).fetchall()

            if not rows:
                logger.info("Settlement batch %s: no pending transactions.", batch_id)

            # Group by node
            node_map: Dict[str, dict] = {}
            for row in rows:
                nid = row["node_id"]
                if nid not in node_map:
                    node_map[nid] = {
                        "node_id": nid,
                        "partner_id": row["partner_id"],
                        "total_bytes": 0,
                        "total_commission": 0.0,
                    }
                node_map[nid]["total_bytes"] += row["bytes_routed"]
                node_map[nid]["total_commission"] += row["commission_earned"]

            total_bytes = sum(n["total_bytes"] for n in node_map.values())
            total_commission = sum(n["total_commission"] for n in node_map.values())

            # Build per-node settlement records
            per_node: Dict[str, NodeSettlement] = {}
            REVENUE_SHARE_PCT = 30.0
            for nid, nd in node_map.items():
                payout = nd["total_commission"] * (REVENUE_SHARE_PCT / 100.0)
                status = (
                    "pending"
                    if payout >= VEIL_SETTLEMENT_MIN_PAYOUT
                    else "below_minimum"
                )
                ns = NodeSettlement(
                    node_id=nid,
                    partner_id=nd["partner_id"],
                    total_bytes=nd["total_bytes"],
                    total_commission=nd["total_commission"],
                    revenue_share_pct=REVENUE_SHARE_PCT,
                    payout_amount=payout,
                    status=status,
                )
                per_node[nid] = ns

                # Insert node record
                conn.execute(
                    """
                    INSERT INTO settlement_node_records
                        (id, batch_id, node_id, partner_id, total_bytes,
                         total_commission, revenue_share_pct, payout_amount, status)
                    VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(uuid.uuid4()),
                        batch_id,
                        nid,
                        nd["partner_id"],
                        nd["total_bytes"],
                        nd["total_commission"],
                        REVENUE_SHARE_PCT,
                        payout,
                        status,
                    ),
                )

            # Insert batch header
            conn.execute(
                """
                INSERT INTO settlement_batches
                    (batch_id, start_time, end_time, total_transactions,
                     total_bytes, total_commission, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    batch_id,
                    _iso(batch_start),
                    _iso(batch_end),
                    len(rows),
                    total_bytes,
                    total_commission,
                    _iso(batch_end),
                ),
            )

            # Mark transactions as settled
            if rows:
                tx_ids = [row["id"] for row in rows]
                placeholders = ",".join("?" * len(tx_ids))
                conn.execute(
                    f"UPDATE settlement_transactions SET settled=1, batch_id=? "
                    f"WHERE id IN ({placeholders})",
                    [batch_id] + tx_ids,
                )

        batch = SettlementBatch(
            batch_id=batch_id,
            start_time=batch_start,
            end_time=batch_end,
            total_transactions=len(rows),
            total_bytes=total_bytes,
            total_commission=total_commission,
            per_node_summary=per_node,
        )

        logger.info(
            "Batch %s | txns=%d bytes=%d commission=%.4f nodes=%d",
            batch_id, len(rows), total_bytes, total_commission, len(per_node),
        )

        # Distribute referral bonuses (best-effort)
        self._process_batch_referral_bonuses(per_node, batch_id)

        # Log to Pantheon (best-effort)
        self._log_batch_to_pantheon(batch)
        # Update Knowledge Graph (best-effort)
        self._update_knowledge_graph(batch)

        return batch

    def get_revenue(self, timeframe: str = "all") -> RevenueResponse:
        """
        Return revenue analytics for a given timeframe.

        Parameters
        ----------
        timeframe : "all" | "today" | "week" | "month"
        """
        now = _utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = today_start.replace(day=1)
        thirty_ago = today_start - timedelta(days=29)

        with self._conn() as conn:
            def _sum(since: Optional[datetime] = None) -> float:
                if since:
                    row = conn.execute(
                        "SELECT COALESCE(SUM(commission_earned),0) "
                        "FROM settlement_transactions WHERE timestamp >= ?",
                        (_iso(since),),
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COALESCE(SUM(commission_earned),0) "
                        "FROM settlement_transactions"
                    ).fetchone()
                return float(row[0])

            total_revenue = _sum()
            revenue_today = _sum(today_start)
            revenue_week = _sum(week_start)
            revenue_month = _sum(month_start)

            # Per-node aggregation
            node_rows = conn.execute(
                """
                SELECT node_id, partner_id,
                       COALESCE(SUM(bytes_routed),0) AS total_bytes,
                       COALESCE(SUM(commission_earned),0) AS total_commission,
                       COUNT(*) AS tx_count
                FROM settlement_transactions
                GROUP BY node_id
                """
            ).fetchall()

            per_node = [
                NodeRevenue(
                    node_id=r["node_id"],
                    partner_id=r["partner_id"],
                    total_bytes=r["total_bytes"],
                    total_commission=r["total_commission"],
                    payout_amount=r["total_commission"] * 0.30,
                    transaction_count=r["tx_count"],
                )
                for r in node_rows
            ]

            # Daily trend (last 30 days)
            daily_rows = conn.execute(
                """
                SELECT DATE(timestamp) AS day,
                       COALESCE(SUM(commission_earned),0) AS commission,
                       COALESCE(SUM(bytes_routed),0) AS bytes,
                       COUNT(*) AS tx_count
                FROM settlement_transactions
                WHERE timestamp >= ?
                GROUP BY day
                ORDER BY day
                """,
                (_iso(thirty_ago),),
            ).fetchall()

            trend = [
                DailyRevenue(
                    date=r["day"],
                    total_commission=r["commission"],
                    total_bytes=r["bytes"],
                    transaction_count=r["tx_count"],
                )
                for r in daily_rows
            ]

        return RevenueResponse(
            total_revenue=total_revenue,
            revenue_today=revenue_today,
            revenue_this_week=revenue_week,
            revenue_this_month=revenue_month,
            per_node_revenue=per_node,
            revenue_trend=trend,
        )

    def get_node_revenue(self, node_id: str) -> Optional[NodeSettlement]:
        """Return the most recent settlement record for a specific node."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM settlement_node_records
                WHERE node_id = ?
                ORDER BY rowid DESC LIMIT 1
                """,
                (node_id,),
            ).fetchone()
            if not row:
                return None
            return NodeSettlement(
                node_id=row["node_id"],
                partner_id=row["partner_id"],
                total_bytes=row["total_bytes"],
                total_commission=row["total_commission"],
                revenue_share_pct=row["revenue_share_pct"],
                payout_amount=row["payout_amount"],
                status=row["status"],
            )

    def prepare_payout(self, node_id: str, amount: float) -> dict:
        """
        Prepare a payment instruction for the external payment processor.

        Returns a dict that can be serialised and forwarded to a payment API.
        """
        from ..config import VEIL_SETTLEMENT_MIN_PAYOUT  # noqa: lazy import

        if amount < VEIL_SETTLEMENT_MIN_PAYOUT:
            return {
                "error": "below_minimum",
                "minimum_usd": VEIL_SETTLEMENT_MIN_PAYOUT,
                "requested_usd": amount,
            }

        payout_id = str(uuid.uuid4())
        now = _utcnow()

        # Fetch partner_id for this node (last known)
        partner_id: Optional[str] = None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT partner_id FROM settlement_node_records "
                "WHERE node_id = ? ORDER BY rowid DESC LIMIT 1",
                (node_id,),
            ).fetchone()
            if row:
                partner_id = row["partner_id"]

            conn.execute(
                """
                INSERT INTO settlement_payouts
                    (payout_id, node_id, partner_id, amount_usd, currency,
                     prepared_at, status, memo)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    payout_id, node_id, partner_id, amount, "USD",
                    _iso(now), "prepared",
                    f"Payout for node {node_id} — {now.date().isoformat()}",
                ),
            )

        instruction = PayoutInstruction(
            payout_id=payout_id,
            node_id=node_id,
            partner_id=partner_id,
            amount_usd=amount,
            prepared_at=now,
        )
        return instruction.model_dump(mode="json")

    def mark_paid(self, settlement_id: str) -> bool:
        """
        Mark a settlement node record (or payout) as paid.

        ``settlement_id`` can be either a ``settlement_node_records.id``
        or a ``settlement_payouts.payout_id``.

        Returns True if any row was updated.
        """
        with self._conn() as conn:
            r1 = conn.execute(
                "UPDATE settlement_node_records SET status='paid' WHERE id=?",
                (settlement_id,),
            )
            r2 = conn.execute(
                "UPDATE settlement_payouts SET status='paid' WHERE payout_id=?",
                (settlement_id,),
            )
        updated = (r1.rowcount + r2.rowcount) > 0
        if updated:
            logger.info("Settlement %s marked as paid.", settlement_id)
        return updated

    def list_batches(self, limit: int = 20) -> List[dict]:
        """Return recent settlement batch headers."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM settlement_batches ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_transactions(
        self,
        page: int = 1,
        page_size: int = 50,
        node_id: Optional[str] = None,
    ) -> dict:
        """Paginated transaction listing."""
        offset = (page - 1) * page_size
        with self._conn() as conn:
            if node_id:
                total = conn.execute(
                    "SELECT COUNT(*) FROM settlement_transactions WHERE node_id=?",
                    (node_id,),
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM settlement_transactions WHERE node_id=? "
                    "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (node_id, page_size, offset),
                ).fetchall()
            else:
                total = conn.execute(
                    "SELECT COUNT(*) FROM settlement_transactions"
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT * FROM settlement_transactions "
                    "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                    (page_size, offset),
                ).fetchall()
        return {
            "transactions": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    # ------------------------------------------------------------------
    # Referral bonus distribution
    # ------------------------------------------------------------------

    def _process_batch_referral_bonuses(
        self, per_node: dict, batch_id: str
    ) -> None:
        """Distribute referral bonuses for all nodes in the batch (best-effort)."""
        try:
            from ..config import VEIL_REFERRAL_ENABLED  # type: ignore
            if not VEIL_REFERRAL_ENABLED:
                return
        except Exception:
            pass  # Default to enabled

        try:
            from ..guardian.referral import referral_service  # type: ignore
        except Exception as exc:
            logger.debug("ReferralService not available for bonus distribution: %s", exc)
            return

        for node_id, ns in per_node.items():
            if not ns.partner_id:
                continue
            try:
                payments = referral_service.process_referral_bonuses(
                    partner_id=ns.partner_id,
                    commission=ns.total_commission,
                    batch_id=batch_id,
                )
                if payments:
                    logger.info(
                        "Batch %s: referral bonuses for node=%s partner=%s: %s",
                        batch_id, node_id, ns.partner_id, payments,
                    )
            except Exception as exc:
                logger.warning(
                    "Referral bonus distribution failed for partner=%s: %s",
                    ns.partner_id, exc,
                )

    # ------------------------------------------------------------------
    # Knowledge Graph + Pantheon integration (best-effort)
    # ------------------------------------------------------------------

    def _log_batch_to_pantheon(self, batch: SettlementBatch) -> None:
        """Write a settlement event to the Pantheon audit log (best-effort)."""
        try:
            from ..services.pantheon.audit_jobs import (  # type: ignore
                log_settlement_event,
            )
            log_settlement_event(
                batch_id=batch.batch_id,
                total_commission=batch.total_commission,
                total_transactions=batch.total_transactions,
            )
        except Exception as exc:
            logger.debug("Pantheon log skipped: %s", exc)

    def _update_knowledge_graph(self, batch: SettlementBatch) -> None:
        """
        Create a Settlement entity in the Knowledge Graph and link it to
        Partner nodes via SETTLES relationships (best-effort).
        """
        try:
            from ..database.manager import get_db  # type: ignore

            db = get_db()
            entity_data = {
                "type": "Settlement",
                "batch_id": batch.batch_id,
                "start_time": _iso(batch.start_time),
                "end_time": _iso(batch.end_time),
                "total_commission": batch.total_commission,
                "node_count": len(batch.per_node_summary),
                "total_transactions": batch.total_transactions,
            }
            entity_id = f"settlement_{batch.batch_id[:8]}"
            db.add_controlled_node(
                node_id=entity_id,
                node_type="Settlement",
                host="internal",
                port=0,
                method="settlement_engine",
            )
            logger.debug("KG entity created: %s", entity_id)
        except Exception as exc:
            logger.debug("KG update skipped: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton (imported by mix_node and main)
# ---------------------------------------------------------------------------

settlement_engine = SettlementEngine()
