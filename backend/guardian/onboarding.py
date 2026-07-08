"""
JULIUS — Partner Onboarding Service
====================================
Manages the full lifecycle of dark-web node-operator (partner) onboarding:

  1. Validate + create a partner record (status='pending').
  2. Generate a unique partner_id, referral_code, and shared secret.
  3. Produce a one-liner install script for the partner to run.
  4. Accept the node's self-registration after install (status→'active').
  5. Integrate with the Knowledge Graph and Settlement engine.
  6. Track referrals and apply revenue-share bonuses.

Database: onboarding.db (SQLite, separate from settlement.db)
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
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
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Banned / reserved IP ranges
# ---------------------------------------------------------------------------

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# OnboardingService
# ---------------------------------------------------------------------------


class OnboardingService:
    """
    Core partner onboarding engine.

    All state is persisted in a local SQLite database (onboarding.db).
    Knowledge Graph and Settlement integrations are best-effort — errors
    are logged but never surface to callers.
    """

    _DB_FILENAME = "onboarding.db"

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            _db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "database",
            )
            os.makedirs(_db_dir, exist_ok=True)
            db_path = os.path.join(_db_dir, self._DB_FILENAME)

        self.db_path = db_path
        self._init_db()

        # Load config with safe fallbacks
        try:
            from ..config import (  # type: ignore
                VEIL_ONBOARDING_MAX_ATTEMPTS,
                VEIL_ONBOARDING_REFERRAL_BONUS,
                VEIL_ONBOARDING_REVENUE_SHARE_DEFAULT,
            )
            self._revenue_share = VEIL_ONBOARDING_REVENUE_SHARE_DEFAULT
            self._referral_bonus = VEIL_ONBOARDING_REFERRAL_BONUS
            self._max_attempts = VEIL_ONBOARDING_MAX_ATTEMPTS
        except Exception:
            self._revenue_share = 0.30
            self._referral_bonus = 0.05
            self._max_attempts = 3

        # Lazy-init referral service (avoids circular imports at module load)
        self._referral_svc = None

        logger.info("OnboardingService initialised — db=%s", self.db_path)

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
        """Create all onboarding tables if they do not already exist."""
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS partners (
                    partner_id          TEXT PRIMARY KEY,
                    node_id             TEXT UNIQUE,
                    node_ip             TEXT NOT NULL,
                    node_name           TEXT,
                    ssh_username        TEXT,
                    referral_code       TEXT UNIQUE NOT NULL,
                    referred_by         TEXT,
                    status              TEXT NOT NULL DEFAULT 'pending',
                    revenue_share_percent REAL NOT NULL DEFAULT 0.30,
                    joined_at           TEXT NOT NULL,
                    last_heartbeat      TEXT,
                    install_attempts    INTEGER NOT NULL DEFAULT 0,
                    public_key          TEXT,
                    metadata            TEXT,
                    contact_info        TEXT,
                    shared_secret       TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_partners_status
                    ON partners (status);
                CREATE INDEX IF NOT EXISTS idx_partners_referral
                    ON partners (referral_code);
                CREATE INDEX IF NOT EXISTS idx_partners_referred_by
                    ON partners (referred_by);

                CREATE TABLE IF NOT EXISTS referral_bonuses (
                    id              TEXT PRIMARY KEY,
                    referrer_id     TEXT NOT NULL,
                    referred_id     TEXT NOT NULL,
                    bonus_percent   REAL NOT NULL DEFAULT 0.05,
                    awarded_at      TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'active'
                );
                """
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _referral_service(self):
        """Lazily load ReferralService to avoid circular imports."""
        if self._referral_svc is None:
            try:
                from ..guardian.referral import ReferralService  # type: ignore
                self._referral_svc = ReferralService()
            except Exception as exc:
                logger.warning("ReferralService unavailable: %s", exc)
        return self._referral_svc

    def start_onboarding(self, request) -> dict:
        """
        Initiate onboarding for a new partner node.

        Steps
        -----
        1. Validate IP (not localhost / private, not already registered).
        2. Resolve referral_code → referred_by partner_id (if provided).
        3. Generate unique partner_id, referral_code, and shared_secret.
        4. Insert partner record (status='pending').
        5. Generate and return the install script + instructions.
        """
        from .install_script import (  # type: ignore
            generate_install_script,
            generate_one_liner,
            generate_shared_secret,
            generate_verification_command,
        )

        # --- Validate IP ---
        node_ip = (request.node_ip or "").strip()
        if not node_ip:
            raise ValueError("node_ip is required")
        if _is_private_ip(node_ip):
            raise ValueError(
                f"IP address '{node_ip}' is private/reserved. "
                "Only public IP addresses may join the network."
            )

        # --- Resolve referral ---
        referred_by: Optional[str] = None
        if request.referral_code:
            referred_by = self._resolve_referral_code(request.referral_code)

        # --- Generate IDs ---
        partner_id = str(uuid.uuid4())

        # Generate referral code via ReferralService (JULIUS-XXXXXXXX format)
        ref_svc = self._referral_service()
        if ref_svc is not None:
            referral_code = ref_svc.generate_referral_code(partner_id)
        else:
            referral_code = self._unique_referral_code()
        shared_secret = generate_shared_secret()
        now = _utcnow()
        revenue_share = self._revenue_share

        # --- Insert partner record ---
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO partners
                    (partner_id, node_ip, node_name, ssh_username,
                     referral_code, referred_by, status,
                     revenue_share_percent, joined_at, install_attempts,
                     shared_secret, contact_info)
                VALUES (?,?,?,?,?,?,?,?,?,0,?,?)
                """,
                (
                    partner_id,
                    node_ip,
                    request.node_name,
                    request.ssh_username,
                    referral_code,
                    referred_by,
                    "pending",
                    revenue_share,
                    _iso(now),
                    shared_secret,
                    request.contact_info,
                ),
            )

        # --- Register referral code in ReferralService ---
        try:
            ref_svc = self._referral_service()
            if ref_svc is not None:
                ref_svc.register_partner_code(partner_id, referral_code)
                # Apply incoming referral code if provided
                if request.referral_code and referred_by:
                    from ..models.referral_models import ApplyReferralRequest  # type: ignore
                    ref_svc.apply_referral(
                        ApplyReferralRequest(
                            referral_code=request.referral_code,
                            partner_id=partner_id,
                        )
                    )
        except Exception as exc:
            logger.warning("ReferralService integration error: %s", exc)

        # --- Build install script ---
        try:
            from ..config import VEIL_ONBOARDING_SSH_KEY_FILE  # type: ignore
            network_url_cfg = os.getenv(
                "VEIL_ONBOARDING_NETWORK_URL", "https://onboarding.julius-veil.net"
            )
        except Exception:
            network_url_cfg = "https://onboarding.julius-veil.net"

        script = generate_install_script(
            partner_id=partner_id,
            shared_secret=shared_secret,
            network_url=network_url_cfg,
            node_name=request.node_name or "",
        )
        one_liner = generate_one_liner(
            partner_id=partner_id, network_url=network_url_cfg
        )
        verification_cmd = generate_verification_command(
            network_url=network_url_cfg, partner_id=partner_id
        )

        instructions = (
            f"JULIUS VEIL Node Onboarding Instructions\n"
            f"{'=' * 50}\n\n"
            f"Your Partner ID : {partner_id}\n"
            f"Your Referral Code: {referral_code}\n\n"
            f"STEP 1 — SSH into your server:\n"
            f"  ssh {request.ssh_username}@{node_ip}\n\n"
            f"STEP 2 — Run the one-liner install command:\n"
            f"  {one_liner}\n\n"
            f"STEP 3 — Verify your node is active:\n"
            f"  {verification_cmd}\n\n"
            f"Your node will automatically register itself with the network\n"
            f"and begin earning {revenue_share * 100:.0f}% revenue share on\n"
            f"all traffic routed through it.\n\n"
            f"Share your referral code to earn an additional "
            f"{self._referral_bonus * 100:.0f}% bonus!\n"
        )

        logger.info(
            "Partner onboarding started: partner_id=%s ip=%s", partner_id, node_ip
        )

        return {
            "partner_id": partner_id,
            "referral_code": referral_code,
            "script": script,
            "one_liner": one_liner,
            "instructions": instructions,
            "verification_command": verification_cmd,
            "status": "pending",
            "revenue_share_percent": revenue_share,
        }

    def register_node(
        self,
        partner_id: str,
        node_public_key: str,
        node_metadata: Optional[dict] = None,
    ) -> bool:
        """
        Called by the install script on the partner node after VEIL installation.

        Steps
        -----
        1. Verify partner_id exists and status is 'pending'.
        2. Update status → 'active'.
        3. Store public_key and metadata.
        4. Add node to Knowledge Graph as 'PartnerNode'.
        5. Award referral bonus if applicable.

        Returns True on success, False if partner_id not found / already active.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM partners WHERE partner_id = ?", (partner_id,)
            ).fetchone()

            if not row:
                logger.warning("register_node: partner_id '%s' not found", partner_id)
                return False

            if row["status"] not in ("pending", "installing", "failed"):
                logger.warning(
                    "register_node: partner_id '%s' already has status '%s'",
                    partner_id,
                    row["status"],
                )
                return False

            # Generate a stable node_id from public_key
            node_id = "partner_" + hashlib.sha256(
                node_public_key.encode()
            ).hexdigest()[:24]

            metadata_json = json.dumps(node_metadata or {})
            now = _utcnow()

            conn.execute(
                """
                UPDATE partners SET
                    node_id = ?,
                    status = 'active',
                    public_key = ?,
                    metadata = ?,
                    last_heartbeat = ?,
                    install_attempts = install_attempts + 1
                WHERE partner_id = ?
                """,
                (node_id, node_public_key, metadata_json, _iso(now), partner_id),
            )

            referred_by = row["referred_by"]

        # --- Knowledge Graph ---
        self._add_to_knowledge_graph(
            partner_id=partner_id,
            node_id=node_id,
            node_ip=row["node_ip"],
            metadata=node_metadata or {},
        )

        # --- Award referral bonus ---
        if referred_by:
            self._award_referral_bonus(referrer_id=referred_by, referred_id=partner_id)

        logger.info(
            "Node registered: partner_id=%s node_id=%s", partner_id, node_id
        )
        return True

    def get_partner_status(self, partner_id: str):
        """Return current partner status as a PartnerStatusResponse."""
        from ..models.partner_models import PartnerStatusResponse  # type: ignore

        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM partners WHERE partner_id = ?", (partner_id,)
            ).fetchone()

        if not row:
            return None

        # Fetch total bytes/commission from settlement engine (best-effort)
        total_bytes, total_commission = self._get_settlement_stats(row["node_id"])

        return PartnerStatusResponse(
            partner_id=row["partner_id"],
            node_id=row["node_id"],
            node_ip=row["node_ip"],
            node_name=row["node_name"],
            status=row["status"],
            joined_at=datetime.fromisoformat(row["joined_at"]),
            last_heartbeat=_parse_dt(row["last_heartbeat"]),
            revenue_share_percent=row["revenue_share_percent"],
            total_bytes_routed=total_bytes,
            total_commission_earned=total_commission,
            referral_code=row["referral_code"],
            referred_by=row["referred_by"],
            install_attempts=row["install_attempts"],
            public_key=row["public_key"],
        )

    def list_partners(self, filters: Optional[dict] = None) -> list:
        """Return all partners (admin only), optionally filtered by status."""
        filters = filters or {}
        clauses = []
        params: list = []

        if "status" in filters and filters["status"]:
            clauses.append("status = ?")
            params.append(filters["status"])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM partners {where} ORDER BY joined_at DESC",
                params,
            ).fetchall()

        result = []
        for row in rows:
            total_bytes, total_commission = self._get_settlement_stats(row["node_id"])
            result.append(
                {
                    "partner_id": row["partner_id"],
                    "node_id": row["node_id"],
                    "node_ip": row["node_ip"],
                    "node_name": row["node_name"],
                    "status": row["status"],
                    "joined_at": row["joined_at"],
                    "last_heartbeat": row["last_heartbeat"],
                    "revenue_share_percent": row["revenue_share_percent"],
                    "referral_code": row["referral_code"],
                    "referred_by": row["referred_by"],
                    "install_attempts": row["install_attempts"],
                    "total_bytes_routed": total_bytes,
                    "total_commission_earned": total_commission,
                }
            )
        return result

    def decommission_partner(self, partner_id: str, reason: str = "") -> bool:
        """Deactivate a partner node (status → 'decommissioned')."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT status FROM partners WHERE partner_id = ?", (partner_id,)
            ).fetchone()

            if not row:
                return False

            conn.execute(
                "UPDATE partners SET status = 'decommissioned' WHERE partner_id = ?",
                (partner_id,),
            )

            # Also deactivate referral bonuses from this partner
            conn.execute(
                "UPDATE referral_bonuses SET status = 'deactivated' WHERE referrer_id = ?",
                (partner_id,),
            )

        logger.info(
            "Partner decommissioned: partner_id=%s reason=%s", partner_id, reason
        )
        return True

    def get_referral_info(self, partner_id: str) -> Optional[dict]:
        """Return referral code, link, and list of referred partners."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT partner_id, referral_code FROM partners WHERE partner_id = ?",
                (partner_id,),
            ).fetchone()

            if not row:
                return None

            referred = conn.execute(
                """
                SELECT partner_id, node_ip, status, joined_at
                FROM partners
                WHERE referred_by = ?
                ORDER BY joined_at DESC
                """,
                (partner_id,),
            ).fetchall()

        try:
            network_url = os.getenv(
                "VEIL_ONBOARDING_NETWORK_URL", "https://onboarding.julius-veil.net"
            )
        except Exception:
            network_url = "https://onboarding.julius-veil.net"

        referral_link = (
            f"{network_url}/join?ref={row['referral_code']}"
        )

        return {
            "partner_id": row["partner_id"],
            "referral_code": row["referral_code"],
            "referral_link": referral_link,
            "referred_partners": [dict(r) for r in referred],
            "total_referrals": len(referred),
            "referral_bonus_percent": self._referral_bonus,
        }

    def generate_referral_code(self, partner_id: str) -> str:
        """Regenerate (or return existing) referral code for a partner."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT referral_code FROM partners WHERE partner_id = ?",
                (partner_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Partner '{partner_id}' not found")
            return row["referral_code"]

    def update_heartbeat(self, partner_id: str) -> bool:
        """Update the last_heartbeat timestamp for an active partner."""
        with self._conn() as conn:
            result = conn.execute(
                "UPDATE partners SET last_heartbeat = ? WHERE partner_id = ?",
                (_iso(_utcnow()), partner_id),
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _unique_referral_code(self) -> str:
        """Generate a unique 8-character uppercase referral code."""
        for _ in range(20):
            code = secrets.token_hex(4).upper()
            with self._conn() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM partners WHERE referral_code = ?", (code,)
                ).fetchone()
            if not exists:
                return code
        # Fallback: use UUID prefix
        return str(uuid.uuid4())[:8].upper()

    def _resolve_referral_code(self, code: str) -> Optional[str]:
        """Resolve a referral code → partner_id. Returns None if invalid."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT partner_id FROM partners WHERE referral_code = ? AND status = 'active'",
                (code,),
            ).fetchone()
        return row["partner_id"] if row else None

    def _award_referral_bonus(self, referrer_id: str, referred_id: str) -> None:
        """Create a referral bonus record linking referrer → referred partner."""
        try:
            with self._conn() as conn:
                # Check if bonus already recorded
                existing = conn.execute(
                    "SELECT 1 FROM referral_bonuses WHERE referrer_id=? AND referred_id=?",
                    (referrer_id, referred_id),
                ).fetchone()
                if existing:
                    return

                conn.execute(
                    """
                    INSERT INTO referral_bonuses
                        (id, referrer_id, referred_id, bonus_percent, awarded_at, status)
                    VALUES (?,?,?,?,?,?)
                    """,
                    (
                        str(uuid.uuid4()),
                        referrer_id,
                        referred_id,
                        self._referral_bonus,
                        _iso(_utcnow()),
                        "active",
                    ),
                )

            # Also update referrer's revenue_share to include the bonus
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT revenue_share_percent FROM partners WHERE partner_id = ?",
                    (referrer_id,),
                ).fetchone()
                if row:
                    new_share = min(
                        row["revenue_share_percent"] + self._referral_bonus, 0.60
                    )
                    conn.execute(
                        "UPDATE partners SET revenue_share_percent = ? WHERE partner_id = ?",
                        (new_share, referrer_id),
                    )

            logger.info(
                "Referral bonus awarded: referrer=%s referred=%s bonus=%.0f%%",
                referrer_id,
                referred_id,
                self._referral_bonus * 100,
            )
        except Exception as exc:
            logger.warning("Could not award referral bonus: %s", exc)

    def _add_to_knowledge_graph(
        self,
        partner_id: str,
        node_id: str,
        node_ip: str,
        metadata: dict,
    ) -> None:
        """Register partner node in the JULIUS Knowledge Graph (best-effort)."""
        try:
            from ..database.manager import get_db  # type: ignore

            db = get_db()
            db.add_controlled_node(
                node_id=node_id,
                node_type="PartnerNode",
                host=node_ip,
                port=0,
                method="partner_onboarding",
            )
            logger.debug("KG entity created: partner_node=%s", node_id)
        except Exception as exc:
            logger.debug("KG upsert skipped for %s: %s", partner_id, exc)

    def _get_settlement_stats(
        self, node_id: Optional[str]
    ) -> tuple[int, float]:
        """Fetch total bytes routed and commission earned from settlement DB."""
        if not node_id:
            return 0, 0.0
        try:
            from ..guardian.settlement import settlement_engine  # type: ignore

            ns = settlement_engine.get_node_revenue(node_id)
            if ns:
                return ns.total_bytes, ns.total_commission
        except Exception:
            pass
        return 0, 0.0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

onboarding_service = OnboardingService()
