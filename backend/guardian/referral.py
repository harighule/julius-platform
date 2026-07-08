"""
JULIUS — Referral Service
=========================
The viral growth engine: every partner earns 5 % of each referred node's
revenue as passive income, creating exponential network expansion.

Key features
------------
* Unique JULIUS-XXXXXXXX referral codes per partner.
* Cooldown period (default 7 days) before bonuses start accruing.
* Multi-level bonus chain (default 3 levels deep).
* Persistent state in referral.db (SQLite, WAL mode).
* Thread-safe context-manager DB connections.

Database layout
---------------
    referrals          — one row per referral relationship
    referral_payments  — one row per bonus payment event
"""

from __future__ import annotations

import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string to a timezone-aware UTC datetime.

    Handles both offset-aware strings (e.g. '2024-01-01T00:00:00+00:00')
    and naive strings (e.g. '2020-01-01T00:00:00') — the latter are assumed
    to be stored in UTC and are made aware by attaching ``timezone.utc``.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            # Naive datetime stored without offset — treat as UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ReferralService
# ---------------------------------------------------------------------------


class ReferralService:
    """
    Core referral engine for JULIUS partner growth.

    All state is persisted in a local SQLite database (referral.db).
    Designed to be integrated with OnboardingService and SettlementEngine.
    """

    _DB_FILENAME = "referral.db"
    _CODE_PREFIX = "JULIUS-"

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            os.makedirs(_db_dir, exist_ok=True)
            db_path = os.path.join(_db_dir, self._DB_FILENAME)

        self.db_path = db_path

        # Load config with safe fallbacks
        try:
            from ..config import (  # type: ignore
                VEIL_REFERRAL_BONUS_PERCENT,
                VEIL_REFERRAL_COOLDOWN_DAYS,
                VEIL_REFERRAL_MAX_LEVELS,
            )
            self.referral_bonus = VEIL_REFERRAL_BONUS_PERCENT
            self.max_levels = VEIL_REFERRAL_MAX_LEVELS
            self.cooldown_days = VEIL_REFERRAL_COOLDOWN_DAYS
        except Exception:
            self.referral_bonus = 0.05
            self.max_levels = 3
            self.cooldown_days = 7

        self._init_db()
        logger.info("ReferralService initialised — db=%s", self.db_path)

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
        """Create all referral tables and indexes if they don't already exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_code       TEXT UNIQUE NOT NULL,
                    referrer_partner_id TEXT NOT NULL,
                    referred_partner_id TEXT UNIQUE,
                    status              TEXT NOT NULL DEFAULT 'pending',
                    applied_at          TEXT DEFAULT (datetime('now')),
                    activated_at        TEXT,
                    bonus_earned        REAL NOT NULL DEFAULT 0.0,
                    cooldown_until      TEXT
                );

                CREATE TABLE IF NOT EXISTS referral_payments (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    referral_id         INTEGER NOT NULL,
                    referrer_partner_id TEXT NOT NULL,
                    amount              REAL NOT NULL DEFAULT 0.0,
                    commission_source   REAL NOT NULL DEFAULT 0.0,
                    level               INTEGER NOT NULL DEFAULT 1,
                    paid_at             TEXT DEFAULT (datetime('now')),
                    settlement_batch_id TEXT,
                    FOREIGN KEY (referral_id) REFERENCES referrals(id)
                );

                CREATE INDEX IF NOT EXISTS idx_referrals_referrer
                    ON referrals (referrer_partner_id);
                CREATE INDEX IF NOT EXISTS idx_referrals_referred
                    ON referrals (referred_partner_id);
                CREATE INDEX IF NOT EXISTS idx_referrals_code
                    ON referrals (referral_code);
                CREATE INDEX IF NOT EXISTS idx_payments_referrer
                    ON referral_payments (referrer_partner_id);
                CREATE INDEX IF NOT EXISTS idx_payments_referral_id
                    ON referral_payments (referral_id);
                """
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_referral_code(self, partner_id: str) -> str:
        """
        Generate a new unique referral code for a partner in the format
        'JULIUS-XXXXXXXX' (8 random uppercase hex chars).

        If the partner already has a code in the referrals table, a new
        code will be created (regenerate use-case) and saved.
        """
        for _ in range(30):
            random_part = secrets.token_hex(4).upper()  # 8 hex chars
            code = f"{self._CODE_PREFIX}{random_part}"
            with self._conn() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM referrals WHERE referral_code = ?", (code,)
                ).fetchone()
            if not exists:
                return code
        # Ultimate fallback: UUID-based
        return f"{self._CODE_PREFIX}{str(uuid.uuid4())[:8].upper()}"

    def register_partner_code(self, partner_id: str, referral_code: str) -> None:
        """
        Register a referral code for a newly onboarded partner so they can
        refer others.  This is idempotent — calling it twice is safe.
        """
        with self._conn() as conn:
            exists = conn.execute(
                "SELECT 1 FROM referrals WHERE referral_code = ?", (referral_code,)
            ).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO referrals
                        (referral_code, referrer_partner_id, status)
                    VALUES (?, ?, 'active')
                    """,
                    (referral_code, partner_id),
                )

    def apply_referral(self, request) -> bool:  # request: ApplyReferralRequest
        """
        Apply a referral code when a new partner onboards.

        Steps
        -----
        1. Validate referral code exists and belongs to an active referrer.
        2. Prevent self-referral.
        3. Check the new partner hasn't already used a referral code.
        4. Link new partner to referrer with a cooldown timestamp.
        5. Activate the referral row.

        Returns True on success, False if validation fails.
        """
        referral_code = request.referral_code.strip().upper()
        new_partner_id = request.partner_id

        with self._conn() as conn:
            # 1. Find the referral row for this code
            row = conn.execute(
                """
                SELECT * FROM referrals
                WHERE referral_code = ? AND status = 'active'
                  AND referred_partner_id IS NULL
                """,
                (referral_code,),
            ).fetchone()

            if not row:
                logger.warning(
                    "apply_referral: code '%s' not found or already used", referral_code
                )
                return False

            referrer_id = row["referrer_partner_id"]

            # 2. Self-referral guard
            if referrer_id == new_partner_id:
                logger.warning(
                    "apply_referral: self-referral attempt by '%s'", new_partner_id
                )
                return False

            # 3. Check new partner hasn't already been referred
            already = conn.execute(
                "SELECT 1 FROM referrals WHERE referred_partner_id = ?",
                (new_partner_id,),
            ).fetchone()
            if already:
                logger.warning(
                    "apply_referral: partner '%s' already has a referral", new_partner_id
                )
                return False

            # 4 + 5. Link and set cooldown
            cooldown_until = _utcnow() + timedelta(days=self.cooldown_days)
            now = _utcnow()

            conn.execute(
                """
                UPDATE referrals
                SET referred_partner_id = ?,
                    activated_at        = ?,
                    cooldown_until      = ?,
                    status              = 'active'
                WHERE id = ?
                """,
                (new_partner_id, _iso(now), _iso(cooldown_until), row["id"]),
            )

        logger.info(
            "Referral applied: referrer=%s new_partner=%s code=%s cooldown_until=%s",
            referrer_id,
            new_partner_id,
            referral_code,
            _iso(cooldown_until),
        )
        return True

    def get_referral_info(self, partner_id: str):  # -> Optional[ReferralInfo]
        """
        Return full referral info (code, link, referred-partner list, earnings)
        for the given partner_id.  Returns None if partner not found.
        """
        from ..models.referral_models import ReferralEarningsResponse, ReferralInfo, ReferredPartner  # type: ignore

        with self._conn() as conn:
            # Get the partner's own referral code row (where they are the referrer
            # and no referred_partner_id set, i.e. their "master" code row)
            own_code_row = conn.execute(
                """
                SELECT referral_code FROM referrals
                WHERE referrer_partner_id = ? AND referred_partner_id IS NULL
                ORDER BY id ASC LIMIT 1
                """,
                (partner_id,),
            ).fetchone()

            if not own_code_row:
                return None

            referral_code = own_code_row["referral_code"]

            # All partners referred by this partner
            referred_rows = conn.execute(
                """
                SELECT r.referred_partner_id, r.activated_at, r.cooldown_until,
                       r.bonus_earned, r.id as referral_id
                FROM referrals r
                WHERE r.referrer_partner_id = ? AND r.referred_partner_id IS NOT NULL
                ORDER BY r.activated_at DESC
                """,
                (partner_id,),
            ).fetchall()

            # Total bonus paid to this partner
            earnings_row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0) as total
                FROM referral_payments
                WHERE referrer_partner_id = ?
                """,
                (partner_id,),
            ).fetchone()
            lifetime_earnings = float(earnings_row["total"])

        # Build ReferredPartner list
        referred_partners = []
        total_active_earnings = 0.0

        for rr in referred_rows:
            rp_id = rr["referred_partner_id"]
            bytes_routed, commission = self._get_partner_stats(rp_id)
            bonus_earned = float(rr["bonus_earned"])
            total_active_earnings += bonus_earned

            # Determine status from onboarding DB
            status = self._get_partner_status(rp_id)
            joined_at = _parse_dt(rr["activated_at"]) or _utcnow()

            referred_partners.append(
                ReferredPartner(
                    partner_id=rp_id,
                    node_id=self._get_partner_node_id(rp_id),
                    joined_at=joined_at,
                    status=status,
                    total_bytes_routed=bytes_routed,
                    total_commission_earned=commission,
                    your_bonus_earned=bonus_earned,
                )
            )

        try:
            base_url = os.getenv(
                "VEIL_ONBOARDING_NETWORK_URL", "https://julius.com"
            )
        except Exception:
            base_url = "https://julius.com"

        referral_link = f"{base_url}/onboarding?ref={referral_code}"

        return ReferralInfo(
            partner_id=partner_id,
            referral_code=referral_code,
            referral_link=referral_link,
            referred_partners=referred_partners,
            total_referred=len(referred_partners),
            total_referral_earnings=total_active_earnings,
            lifetime_referral_earnings=lifetime_earnings,
        )

    def get_referral_tree(self, partner_id: str, max_depth: Optional[int] = None):
        """
        Build a multi-level referral tree starting from the given partner.
        Depth is capped at self.max_levels (default 3).
        """
        from ..models.referral_models import ReferralTree  # type: ignore

        depth_limit = min(max_depth or self.max_levels, self.max_levels)

        def _build_subtree(pid: str, current_depth: int) -> dict:
            if current_depth > depth_limit:
                return {}
            with self._conn() as conn:
                children = conn.execute(
                    """
                    SELECT referred_partner_id, activated_at
                    FROM referrals
                    WHERE referrer_partner_id = ?
                      AND referred_partner_id IS NOT NULL
                    """,
                    (pid,),
                ).fetchall()

            subtree: dict = {}
            for child in children:
                cid = child["referred_partner_id"]
                subtree[cid] = {
                    "partner_id": cid,
                    "node_id": self._get_partner_node_id(cid),
                    "status": self._get_partner_status(cid),
                    "joined_at": child["activated_at"],
                    "level": current_depth,
                    "children": _build_subtree(cid, current_depth + 1),
                }

            return subtree

        tree = _build_subtree(partner_id, 1)

        # Calculate actual depth
        def _tree_depth(node: dict) -> int:
            if not node:
                return 0
            return 1 + max(
                (_tree_depth(v.get("children", {})) for v in node.values()), default=0
            )

        actual_depth = _tree_depth(tree)

        return ReferralTree(root=partner_id, depth=actual_depth, tree=tree)

    def calculate_referral_bonus(self, partner_id: str, commission: float) -> float:
        """
        Calculate the bonus a referrer should earn from a referred partner's
        commission.  Returns commission * referral_bonus_percent.
        """
        return commission * self.referral_bonus

    def process_referral_bonuses(
        self,
        partner_id: str,
        commission: float,
        batch_id: Optional[str] = None,
    ) -> dict:
        """
        Distribute referral bonuses up the referral chain for up to max_levels.

        For each ancestor level:
            bonus = commission * referral_bonus_percent

        Returns a dict summarising all payments made:
            {referrer_partner_id: amount_paid, ...}
        """
        payments: Dict[str, float] = {}

        # Walk UP the chain: find who referred this partner, then who referred
        # that referrer, and so on up to max_levels.
        current_partner = partner_id
        level = 1

        while level <= self.max_levels:
            referrer_id, referral_id = self._get_referrer(current_partner)
            if not referrer_id or not referral_id:
                break  # No more referrers in the chain

            # Check cooldown: bonus only applies after cooldown expires
            if self._is_in_cooldown(referral_id):
                logger.debug(
                    "Referral %d still in cooldown — skipping bonus for level %d",
                    referral_id,
                    level,
                )
                current_partner = referrer_id
                level += 1
                continue

            bonus = commission * self.referral_bonus
            if bonus <= 0:
                current_partner = referrer_id
                level += 1
                continue

            # Record the payment
            self._record_referral_payment(
                referral_id=referral_id,
                referrer_partner_id=referrer_id,
                amount=bonus,
                commission_source=commission,
                level=level,
                batch_id=batch_id,
            )

            payments[referrer_id] = payments.get(referrer_id, 0.0) + bonus
            logger.info(
                "Referral bonus L%d: referrer=%s amount=%.6f (from commission=%.6f)",
                level,
                referrer_id,
                bonus,
                commission,
            )

            current_partner = referrer_id
            level += 1

        return payments

    def get_referral_earnings(self, partner_id: str) -> dict:
        """Return a summary of all referral earnings for a partner."""
        with self._conn() as conn:
            # Total bonus earned
            total_row = conn.execute(
                """
                SELECT COALESCE(SUM(amount), 0.0) as total
                FROM referral_payments
                WHERE referrer_partner_id = ?
                """,
                (partner_id,),
            ).fetchone()

            # Number of active referrals
            active_row = conn.execute(
                """
                SELECT COUNT(*) as cnt
                FROM referrals
                WHERE referrer_partner_id = ?
                  AND referred_partner_id IS NOT NULL
                  AND status = 'active'
                """,
                (partner_id,),
            ).fetchone()

            total_row2 = conn.execute(
                """
                SELECT COUNT(*) as cnt
                FROM referrals
                WHERE referrer_partner_id = ?
                  AND referred_partner_id IS NOT NULL
                """,
                (partner_id,),
            ).fetchone()

            # Pending cooldown
            cooldown_row = conn.execute(
                """
                SELECT COUNT(*) as cnt
                FROM referrals
                WHERE referrer_partner_id = ?
                  AND referred_partner_id IS NOT NULL
                  AND cooldown_until > ?
                """,
                (partner_id, _iso(_utcnow())),
            ).fetchone()

            # Own referral code
            own_code = conn.execute(
                """
                SELECT referral_code FROM referrals
                WHERE referrer_partner_id = ? AND referred_partner_id IS NULL
                ORDER BY id ASC LIMIT 1
                """,
                (partner_id,),
            ).fetchone()

            # Recent payments
            payments = conn.execute(
                """
                SELECT amount, commission_source, level, paid_at, settlement_batch_id
                FROM referral_payments
                WHERE referrer_partner_id = ?
                ORDER BY paid_at DESC
                LIMIT 50
                """,
                (partner_id,),
            ).fetchall()

        return {
            "partner_id": partner_id,
            "referral_code": own_code["referral_code"] if own_code else None,
            "total_referred": total_row2["cnt"],
            "active_referred": active_row["cnt"],
            "total_bonus_earned": float(total_row["total"]),
            "lifetime_bonus_earned": float(total_row["total"]),
            "pending_cooldown": cooldown_row["cnt"],
            "payments": [dict(p) for p in payments],
        }

    def get_analytics(self) -> dict:
        """Return platform-wide referral analytics (admin only)."""
        with self._conn() as conn:
            total_created = conn.execute(
                "SELECT COUNT(*) as cnt FROM referrals WHERE referred_partner_id IS NOT NULL"
            ).fetchone()["cnt"]

            active_cnt = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM referrals
                WHERE status = 'active' AND referred_partner_id IS NOT NULL
                """
            ).fetchone()["cnt"]

            pending_cnt = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM referrals
                WHERE status = 'pending'
                """
            ).fetchone()["cnt"]

            total_paid_row = conn.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM referral_payments"
            ).fetchone()

            # Top referrers: partners who have brought in the most active referrals
            top_rows = conn.execute(
                """
                SELECT referrer_partner_id,
                       COUNT(*) as total_referred,
                       SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active_referred,
                       COALESCE(
                           (SELECT SUM(rp.amount) FROM referral_payments rp
                            WHERE rp.referrer_partner_id = r.referrer_partner_id), 0.0
                       ) as total_bonus
                FROM referrals r
                WHERE referred_partner_id IS NOT NULL
                GROUP BY referrer_partner_id
                ORDER BY total_referred DESC
                LIMIT 10
                """
            ).fetchall()

            # Get referral codes for top referrers
            top_referrers = []
            for tr in top_rows:
                pid = tr["referrer_partner_id"]
                code_row = conn.execute(
                    """
                    SELECT referral_code FROM referrals
                    WHERE referrer_partner_id = ? AND referred_partner_id IS NULL
                    ORDER BY id ASC LIMIT 1
                    """,
                    (pid,),
                ).fetchone()
                top_referrers.append(
                    {
                        "partner_id": pid,
                        "referral_code": code_row["referral_code"] if code_row else "",
                        "total_referred": tr["total_referred"],
                        "active_referred": tr["active_referred"],
                        "total_bonus_earned": float(tr["total_bonus"]),
                    }
                )

        return {
            "total_referrals_created": total_created,
            "active_referrals": active_cnt,
            "pending_referrals": pending_cnt,
            "total_referral_bonus_paid": float(total_paid_row["total"]),
            "top_referrers": top_referrers,
            "referral_bonus_percent": self.referral_bonus,
            "max_levels": self.max_levels,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_referrer(
        self, partner_id: str
    ) -> tuple[Optional[str], Optional[int]]:
        """
        Return (referrer_partner_id, referral_id) for the given partner.
        Returns (None, None) if no referral record found.
        """
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, referrer_partner_id
                FROM referrals
                WHERE referred_partner_id = ?
                  AND status = 'active'
                LIMIT 1
                """,
                (partner_id,),
            ).fetchone()
        if row:
            return row["referrer_partner_id"], row["id"]
        return None, None

    def _is_in_cooldown(self, referral_id: int) -> bool:
        """Return True if the referral is still within its cooldown window.

        Always compares two UTC-aware datetimes to avoid
        ``TypeError: can't compare offset-naive and offset-aware datetimes``
        on rows written before the timezone-aware migration.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cooldown_until FROM referrals WHERE id = ?",
                (referral_id,),
            ).fetchone()
        if not row or not row["cooldown_until"]:
            return False
        cooldown_until = _parse_dt(row["cooldown_until"])  # always UTC-aware
        if not cooldown_until:
            return False
        return _utcnow() < cooldown_until

    def _record_referral_payment(
        self,
        referral_id: int,
        referrer_partner_id: str,
        amount: float,
        commission_source: float,
        level: int,
        batch_id: Optional[str] = None,
    ) -> None:
        """Persist a referral bonus payment and update cumulative bonus_earned."""
        now = _utcnow()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO referral_payments
                    (referral_id, referrer_partner_id, amount, commission_source,
                     level, paid_at, settlement_batch_id)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    referral_id,
                    referrer_partner_id,
                    amount,
                    commission_source,
                    level,
                    _iso(now),
                    batch_id,
                ),
            )
            # Update cumulative bonus on the referral row
            conn.execute(
                "UPDATE referrals SET bonus_earned = bonus_earned + ? WHERE id = ?",
                (amount, referral_id),
            )

    def _get_partner_stats(
        self, partner_id: str
    ) -> tuple[int, float]:
        """Fetch bytes routed + commission from settlement DB (best-effort)."""
        try:
            from ..guardian.settlement import settlement_engine  # type: ignore

            # Look up node_id from onboarding DB
            node_id = self._get_partner_node_id(partner_id)
            if not node_id:
                return 0, 0.0
            ns = settlement_engine.get_node_revenue(node_id)
            if ns:
                return ns.total_bytes, ns.total_commission
        except Exception:
            pass
        return 0, 0.0

    def _get_partner_node_id(self, partner_id: str) -> Optional[str]:
        """Look up node_id from the onboarding DB (best-effort)."""
        try:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            onboarding_db = os.path.join(_db_dir, "onboarding.db")
            if not os.path.exists(onboarding_db):
                return None
            with sqlite3.connect(onboarding_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT node_id FROM partners WHERE partner_id = ?",
                    (partner_id,),
                ).fetchone()
            return row["node_id"] if row else None
        except Exception:
            return None

    def _get_partner_status(self, partner_id: str) -> str:
        """Look up partner status from onboarding DB (best-effort)."""
        try:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            onboarding_db = os.path.join(_db_dir, "onboarding.db")
            if not os.path.exists(onboarding_db):
                return "unknown"
            with sqlite3.connect(onboarding_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT status FROM partners WHERE partner_id = ?",
                    (partner_id,),
                ).fetchone()
            return row["status"] if row else "unknown"
        except Exception:
            return "unknown"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

referral_service = ReferralService()
