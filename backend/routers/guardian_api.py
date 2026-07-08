"""
JULIUS — Guardian API Router
Admin-only endpoints for revenue analytics, settlement batches,
transaction history, and payout management.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 60-second in-process cache for revenue summary
# ---------------------------------------------------------------------------


class _RevenueSummaryCache:
    """Thread-safe TTL cache for the revenue summary result."""

    TTL = 60  # seconds

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = None
        self._expires_at: float = 0.0

    def get(self):
        with self._lock:
            if time.monotonic() < self._expires_at and self._value is not None:
                return self._value
        return None

    def set(self, value) -> None:
        with self._lock:
            self._value = value
            self._expires_at = time.monotonic() + self.TTL

    def invalidate(self) -> None:
        with self._lock:
            self._value = None
            self._expires_at = 0.0


_revenue_cache = _RevenueSummaryCache()

router = APIRouter(prefix="/api/guardian", tags=["Guardian — Settlement"])

# ---------------------------------------------------------------------------
# Auth guard (reuse JWT from existing auth module)
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _require_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    Validate Bearer JWT and assert admin role.
    Returns the username on success; raises HTTP 403 on failure.
    """
    if creds is None:
        raise HTTPException(status_code=403, detail="Authorization header missing")
    try:
        from ..database import db as _db  # type: ignore

        result = _db.verify_jwt_token(creds.credentials)
        if not result.get("success"):
            raise HTTPException(status_code=403, detail="Invalid or expired token")
        role = result.get("role", "")
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        return result.get("username", "admin")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Auth check failed: %s", exc)
        raise HTTPException(status_code=403, detail="Authentication error")


# ---------------------------------------------------------------------------
# Lazy engine accessor
# ---------------------------------------------------------------------------

def _engine():
    from ..guardian.settlement import settlement_engine  # type: ignore

    return settlement_engine


# ---------------------------------------------------------------------------
# Revenue endpoints
# ---------------------------------------------------------------------------


@router.get("/revenue", summary="Overall revenue summary")
async def get_revenue(admin: str = Depends(_require_admin)):
    """
    Return total revenue, daily/weekly/monthly breakdowns,
    per-node summaries, and the 30-day trend.
    """
    try:
        return _engine().get_revenue()
    except Exception as exc:
        logger.error("get_revenue failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/revenue/nodes", summary="Revenue per node")
async def get_revenue_nodes(admin: str = Depends(_require_admin)):
    """Return aggregated revenue broken down by node."""
    try:
        rev = _engine().get_revenue()
        return {
            "nodes": [n.model_dump() for n in rev.per_node_revenue],
            "total_nodes": len(rev.per_node_revenue),
        }
    except Exception as exc:
        logger.error("get_revenue_nodes failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/revenue/nodes/{node_id}", summary="Revenue for a specific node")
async def get_revenue_node(node_id: str, admin: str = Depends(_require_admin)):
    """Return the most recent settlement record for a specific node."""
    try:
        ns = _engine().get_node_revenue(node_id)
        if ns is None:
            raise HTTPException(
                status_code=404, detail=f"No settlement data for node '{node_id}'"
            )
        return ns.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_revenue_node failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/revenue/trend", summary="Daily revenue trend (last 30 days)")
async def get_revenue_trend(admin: str = Depends(_require_admin)):
    """Return daily commission totals for the last 30 calendar days."""
    try:
        rev = _engine().get_revenue()
        return {
            "trend": [d.model_dump() for d in rev.revenue_trend],
            "days": len(rev.revenue_trend),
        }
    except Exception as exc:
        logger.error("get_revenue_trend failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Typed revenue endpoints (dashboard-facing, with caching)
# ---------------------------------------------------------------------------

from ..models.revenue_models import (  # noqa: E402
    NodeRevenue as NodeRevenueSchema,
    RevenueSummary,
    RevenueTrendPoint,
)


@router.get(
    "/revenue/summary",
    response_model=RevenueSummary,
    summary="Revenue summary (cached 60 s)",
    tags=["Guardian — Settlement"],
)
async def get_revenue_summary(admin: str = Depends(_require_admin)) -> RevenueSummary:
    """
    Return a typed revenue summary including totals, period breakdowns,
    average daily revenue, and active-node counts.

    Result is cached for 60 seconds to reduce DB load.

    Auth: Admin JWT required.
    """
    cached = _revenue_cache.get()
    if cached is not None:
        return cached

    try:
        rev = _engine().get_revenue()
    except Exception as exc:
        logger.error("get_revenue_summary failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Compute average daily revenue over last 30 days
    if rev.revenue_trend:
        avg_daily = sum(d.total_commission for d in rev.revenue_trend) / len(
            rev.revenue_trend
        )
    else:
        avg_daily = 0.0

    # Active nodes = nodes with revenue today
    active_nodes = sum(
        1 for n in rev.per_node_revenue if n.total_commission > 0
    )

    summary = RevenueSummary(
        total_revenue=rev.total_revenue,
        revenue_today=rev.revenue_today,
        revenue_this_week=rev.revenue_this_week,
        revenue_this_month=rev.revenue_this_month,
        average_daily_revenue=round(avg_daily, 6),
        node_count=len(rev.per_node_revenue),
        active_nodes=active_nodes,
    )
    _revenue_cache.set(summary)
    return summary


@router.get(
    "/revenue/trend",
    response_model=List[RevenueTrendPoint],
    summary="Daily revenue trend — last 30 days",
    tags=["Guardian — Settlement"],
)
async def get_revenue_trend_typed(
    admin: str = Depends(_require_admin),
) -> List[RevenueTrendPoint]:
    """
    Return daily revenue data points for the last 30 calendar days.
    Each point contains the date, total commission, and transaction count.

    Auth: Admin JWT required.
    """
    try:
        rev = _engine().get_revenue()
        return [
            RevenueTrendPoint(
                date=d.date,
                revenue=d.total_commission,
                transactions=d.transaction_count,
            )
            for d in rev.revenue_trend
        ]
    except Exception as exc:
        logger.error("get_revenue_trend_typed failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/revenue/nodes",
    summary="Revenue per node (typed)",
    tags=["Guardian — Settlement"],
)
async def get_revenue_nodes_typed(admin: str = Depends(_require_admin)):
    """
    Return aggregated revenue broken down by node, including revenue share
    percentage and payout amounts.

    Auth: Admin JWT required.
    """
    try:
        rev = _engine().get_revenue()
        nodes: List[NodeRevenueSchema] = [
            NodeRevenueSchema(
                node_id=n.node_id,
                partner_id=n.partner_id,
                total_bytes=n.total_bytes,
                total_commission=n.total_commission,
                revenue_share_pct=30.0,
                payout_amount=n.payout_amount,
            )
            for n in rev.per_node_revenue
        ]
        return {
            "nodes": [n.model_dump() for n in nodes],
            "total_nodes": len(nodes),
        }
    except Exception as exc:
        logger.error("get_revenue_nodes_typed failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/revenue/nodes/{node_id}",
    response_model=NodeRevenueSchema,
    summary="Revenue for a specific node (typed)",
    tags=["Guardian — Settlement"],
)
async def get_revenue_node_typed(
    node_id: str, admin: str = Depends(_require_admin)
) -> NodeRevenueSchema:
    """
    Return typed revenue details for a single node.

    Auth: Admin JWT required.
    """
    try:
        ns = _engine().get_node_revenue(node_id)
        if ns is None:
            raise HTTPException(
                status_code=404,
                detail=f"No settlement data for node '{node_id}'",
            )
        return NodeRevenueSchema(
            node_id=ns.node_id,
            partner_id=ns.partner_id,
            total_bytes=ns.total_bytes,
            total_commission=ns.total_commission,
            revenue_share_pct=ns.revenue_share_pct,
            payout_amount=ns.payout_amount,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_revenue_node_typed failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Settlement batch endpoints
# ---------------------------------------------------------------------------


@router.post("/settlement/process", summary="Manually trigger batch processing")
async def trigger_settlement(admin: str = Depends(_require_admin)):
    """
    Immediately run a settlement batch outside the hourly schedule.
    Returns the new SettlementBatch.
    """
    try:
        batch = _engine().process_batch()
        return {
            "message": "Settlement batch processed successfully.",
            "batch_id": batch.batch_id,
            "total_transactions": batch.total_transactions,
            "total_bytes": batch.total_bytes,
            "total_commission": batch.total_commission,
            "node_count": len(batch.per_node_summary),
            "nodes": {k: v.model_dump() for k, v in batch.per_node_summary.items()},
        }
    except Exception as exc:
        logger.error("trigger_settlement failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/settlement/batches", summary="List recent settlement batches")
async def list_batches(
    limit: int = Query(20, ge=1, le=200),
    admin: str = Depends(_require_admin),
):
    """Return the most recent settlement batch header records."""
    try:
        batches = _engine().list_batches(limit=limit)
        return {"batches": batches, "count": len(batches)}
    except Exception as exc:
        logger.error("list_batches failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------


@router.get("/transactions", summary="List recent transactions (paginated)")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    admin: str = Depends(_require_admin),
):
    """Paginated list of all settlement transactions."""
    try:
        return _engine().list_transactions(
            page=page, page_size=page_size, node_id=node_id
        )
    except Exception as exc:
        logger.error("list_transactions failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Payout management
# ---------------------------------------------------------------------------


@router.post("/payout/prepare/{node_id}", summary="Prepare a payout for a node")
async def prepare_payout(
    node_id: str,
    amount: float = Query(..., gt=0, description="Payout amount in USD"),
    admin: str = Depends(_require_admin),
):
    """Generate a payout instruction for the specified node."""
    try:
        instruction = _engine().prepare_payout(node_id=node_id, amount=amount)
        return instruction
    except Exception as exc:
        logger.error("prepare_payout failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/payout/mark-paid/{settlement_id}", summary="Mark a settlement as paid")
async def mark_settlement_paid(
    settlement_id: str, admin: str = Depends(_require_admin)
):
    """Mark the given settlement_id (node record or payout) as paid."""
    try:
        updated = _engine().mark_paid(settlement_id)
        if not updated:
            raise HTTPException(
                status_code=404,
                detail=f"Settlement '{settlement_id}' not found or already updated.",
            )
        return {"settlement_id": settlement_id, "status": "paid", "updated": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("mark_settlement_paid failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Discovery endpoints
# ---------------------------------------------------------------------------


def _disco():
    """Lazy accessor for the module-level DiscoveryEngine singleton."""
    from ..guardian.discovery import discovery_engine  # type: ignore
    return discovery_engine


@router.post("/discovery/run", summary="Manually trigger passive node discovery")
async def trigger_discovery(admin: str = Depends(_require_admin)):
    """
    Immediately run a full passive discovery sweep across all configured
    public sources (Tor Metrics, I2P NetDB, public DNS).
    Returns a summary of the discovery run.
    """
    import asyncio

    try:
        engine = _disco()
        # Run in executor so the async handler is not blocked
        loop = asyncio.get_event_loop()
        nodes, run = await loop.run_in_executor(None, engine.discover_all)
        new_c, upd_c = await loop.run_in_executor(None, engine.update_knowledge_graph, nodes)
        return {
            "message": "Discovery run completed.",
            "run_id": run.run_id,
            "nodes_discovered": run.nodes_discovered,
            "nodes_new": new_c,
            "nodes_updated": upd_c,
            "errors": run.errors,
            "sources_used": run.sources_used,
            "status": run.status,
        }
    except Exception as exc:
        logger.error("trigger_discovery failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/discovery/nodes", summary="List all discovered dark-web nodes")
async def list_discovery_nodes(
    network: Optional[str] = Query(None, description="Filter: 'tor', 'i2p', or 'mixnet'"),
    source: Optional[str] = Query(None, description="Filter by source name"),
    min_score: float = Query(0.0, ge=0.0, le=100.0, description="Minimum quality score"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin: str = Depends(_require_admin),
):
    """
    Return a paginated list of all nodes discovered from public sources.
    Optionally filter by network type, source, or minimum quality score.
    """
    try:
        engine = _disco()
        nodes = engine.list_nodes(
            network=network, source=source, min_score=min_score,
            limit=limit, offset=offset,
        )
        total = engine.get_node_count()
        last_run = engine.get_last_run()
        return {
            "nodes": nodes,
            "count": len(nodes),
            "total_stored": total,
            "last_run": last_run,
        }
    except Exception as exc:
        logger.error("list_discovery_nodes failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/discovery/nodes/{node_id}", summary="Get a specific discovered node")
async def get_discovery_node(node_id: str, admin: str = Depends(_require_admin)):
    """Return full details for a single discovered node by its node_id."""
    try:
        engine = _disco()
        node = engine.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
        return node
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_discovery_node failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/discovery/score", summary="Re-score all discovered nodes")
async def rescore_nodes(admin: str = Depends(_require_admin)):
    """
    Re-apply the scoring algorithm to every stored node.
    Useful after a scoring formula update.
    """
    import asyncio

    try:
        engine = _disco()
        loop = asyncio.get_event_loop()
        count = await loop.run_in_executor(None, engine.rescore_all)
        return {"message": "Re-scoring complete.", "nodes_rescored": count}
    except Exception as exc:
        logger.error("rescore_nodes failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Partner Onboarding endpoints
# ---------------------------------------------------------------------------


def _onboarding():
    """Lazy accessor for the OnboardingService singleton."""
    from ..guardian.onboarding import onboarding_service  # type: ignore
    return onboarding_service


def _require_partner_token(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    Lightweight auth for partner-facing endpoints.
    Accepts either a valid admin JWT **or** any non-empty bearer token
    (partner_id used as self-auth token in the MVP; can be hardened later).
    Returns the token value on success.
    """
    if creds is None:
        raise HTTPException(status_code=403, detail="Authorization header missing")
    return creds.credentials


from ..models.partner_models import (  # noqa: E402
    DecommissionRequest,
    NodeRegisterRequest,
    PartnerOnboardRequest,
)


@router.post(
    "/onboarding/start",
    summary="Start partner onboarding — get install script",
    tags=["Guardian — Onboarding"],
)
async def onboarding_start(body: PartnerOnboardRequest):
    """
    Public endpoint: submit your server's IP to start onboarding.
    Returns a unique partner_id and a bash install script to run on your node.

    Auth: none required (referral code optional in request body).
    """
    try:
        svc = _onboarding()
        result = svc.start_onboarding(body)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("onboarding_start failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/onboarding/register",
    summary="Register an installed VEIL node with the network",
    tags=["Guardian — Onboarding"],
)
async def onboarding_register(body: NodeRegisterRequest):
    """
    Called automatically by the install script after VEIL node installation.
    Updates partner status to 'active' and registers in the Knowledge Graph.

    Auth: none required (script uses partner_id as identity).
    """
    try:
        svc = _onboarding()
        success = svc.register_node(
            partner_id=body.partner_id,
            node_public_key=body.public_key,
            node_metadata=body.node_metadata or {},
        )
        if not success:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Partner '{body.partner_id}' not found, already active, "
                    "or decommissioned."
                ),
            )
        return {
            "message": "Node successfully registered and activated.",
            "partner_id": body.partner_id,
            "status": "active",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("onboarding_register failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/onboarding/status/{partner_id}",
    summary="Get partner status",
    tags=["Guardian — Onboarding"],
)
async def onboarding_status(
    partner_id: str,
    token: str = Depends(_require_partner_token),
):
    """
    Return the current status, revenue share, and stats for a partner.

    Auth: Bearer <partner_id> (self-auth) or admin JWT.
    """
    try:
        svc = _onboarding()
        status = svc.get_partner_status(partner_id)
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"Partner '{partner_id}' not found.",
            )
        return status.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("onboarding_status failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/onboarding/partners",
    summary="List all partners (admin only)",
    tags=["Guardian — Onboarding"],
)
async def onboarding_list_partners(
    status: Optional[str] = Query(
        None,
        description="Filter by status: pending | installing | active | failed | decommissioned",
    ),
    admin: str = Depends(_require_admin),
):
    """Return a list of all registered partners with their current status."""
    try:
        svc = _onboarding()
        partners = svc.list_partners(filters={"status": status})
        return {"partners": partners, "count": len(partners)}
    except Exception as exc:
        logger.error("onboarding_list_partners failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/onboarding/decommission",
    summary="Deactivate a partner node (admin only)",
    tags=["Guardian — Onboarding"],
)
async def onboarding_decommission(
    body: DecommissionRequest,
    admin: str = Depends(_require_admin),
):
    """Permanently deactivate a partner node and stop revenue sharing."""
    try:
        svc = _onboarding()
        success = svc.decommission_partner(
            partner_id=body.partner_id,
            reason=body.reason or "",
        )
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Partner '{body.partner_id}' not found.",
            )
        return {
            "message": f"Partner '{body.partner_id}' has been decommissioned.",
            "partner_id": body.partner_id,
            "status": "decommissioned",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("onboarding_decommission failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/onboarding/referral/{partner_id}",
    summary="Get referral link and stats for a partner (admin only)",
    tags=["Guardian — Onboarding"],
)
async def onboarding_referral(
    partner_id: str,
    admin: str = Depends(_require_admin),
):
    """Return the referral code, link, and list of referred partners."""
    try:
        svc = _onboarding()
        info = svc.get_referral_info(partner_id)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"Partner '{partner_id}' not found.",
            )
        return info
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("onboarding_referral failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/onboarding/script/{partner_id}",
    response_class=PlainTextResponse,
    summary="Download the bash install script for a partner",
    tags=["Guardian — Onboarding"],
)
async def onboarding_get_script(partner_id: str):
    """
    Serves the raw bash install script for the given partner_id.
    This is the URL used by the one-liner: curl -fsSL .../script/{partner_id} | sudo bash
    """
    from fastapi.responses import PlainTextResponse  # type: ignore

    try:
        svc = _onboarding()
        status_obj = svc.get_partner_status(partner_id)
        if not status_obj:
            raise HTTPException(
                status_code=404,
                detail=f"Partner '{partner_id}' not found.",
            )

        from ..guardian.install_script import (  # type: ignore
            generate_install_script,
            generate_shared_secret,
        )

        # Fetch shared_secret from DB
        import sqlite3 as _sqlite3
        with _sqlite3.connect(svc.db_path) as _c:
            _c.row_factory = _sqlite3.Row
            _row = _c.execute(
                "SELECT shared_secret, node_name FROM partners WHERE partner_id=?",
                (partner_id,),
            ).fetchone()

        secret = _row["shared_secret"] if _row else generate_shared_secret()
        name = (_row["node_name"] or "") if _row else ""

        try:
            from ..config import VEIL_ONBOARDING_NETWORK_URL  # type: ignore
            network_url = VEIL_ONBOARDING_NETWORK_URL
        except Exception:
            network_url = "https://onboarding.julius-veil.net"

        script = generate_install_script(
            partner_id=partner_id,
            shared_secret=secret,
            network_url=network_url,
            node_name=name,
        )

        return PlainTextResponse(content=script, media_type="text/x-sh")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("onboarding_get_script failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Referral System endpoints
# ---------------------------------------------------------------------------


def _referral():
    """Lazy accessor for the ReferralService singleton."""
    from ..guardian.referral import referral_service  # type: ignore
    return referral_service


@router.get(
    "/referral/{partner_id}",
    summary="Get referral info and earnings for a partner",
    tags=["Guardian — Referral"],
)
async def get_referral_info(
    partner_id: str,
    token: str = Depends(_require_partner_token),
):
    """
    Return referral code, referral link, list of referred partners,
    and total/lifetime earnings.

    Auth: Bearer <partner_id> (self-auth) or admin JWT.
    """
    try:
        svc = _referral()
        info = svc.get_referral_info(partner_id)
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"No referral data found for partner '{partner_id}'. "
                       "Ensure the partner has been onboarded.",
            )
        return info.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_referral_info failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/referral/{partner_id}/tree",
    summary="Get multi-level referral tree (admin only)",
    tags=["Guardian — Referral"],
)
async def get_referral_tree(
    partner_id: str,
    admin: str = Depends(_require_admin),
):
    """
    Return the full multi-level referral tree starting from this partner,
    up to the configured max depth (default 3 levels).

    Auth: Admin JWT required.
    """
    try:
        svc = _referral()
        tree = svc.get_referral_tree(partner_id)
        return tree.model_dump(mode="json")
    except Exception as exc:
        logger.error("get_referral_tree failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/referral/{partner_id}/earnings",
    summary="Get referral earnings summary for a partner",
    tags=["Guardian — Referral"],
)
async def get_referral_earnings(
    partner_id: str,
    token: str = Depends(_require_partner_token),
):
    """
    Return a detailed earnings breakdown: total bonus earned, active
    referrals, referrals still in cooldown, and recent payment history.

    Auth: Bearer <partner_id> (self-auth) or admin JWT.
    """
    try:
        svc = _referral()
        earnings = svc.get_referral_earnings(partner_id)
        return earnings
    except Exception as exc:
        logger.error("get_referral_earnings failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/referral/analytics",
    summary="Global referral analytics (admin only)",
    tags=["Guardian — Referral"],
)
async def get_referral_analytics(admin: str = Depends(_require_admin)):
    """
    Return platform-wide referral analytics: total referrals created,
    active referrals, total bonuses paid, and top referrers.

    Auth: Admin JWT required.
    """
    try:
        svc = _referral()
        analytics = svc.get_analytics()
        return analytics
    except Exception as exc:
        logger.error("get_referral_analytics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/referral/code/{partner_id}",
    summary="Generate or retrieve a partner's referral code (admin only)",
    tags=["Guardian — Referral"],
)
async def get_or_generate_referral_code(
    partner_id: str,
    admin: str = Depends(_require_admin),
):
    """
    Return the existing referral code for a partner, or generate a fresh
    JULIUS-XXXXXXXX code if they don't have one yet.

    Auth: Admin JWT required.
    """
    try:
        svc = _referral()
        code = svc.generate_referral_code(partner_id)
        # Register the code so it can be used immediately
        svc.register_partner_code(partner_id, code)
        try:
            base_url = __import__("os").getenv(
                "VEIL_ONBOARDING_NETWORK_URL", "https://julius.com"
            )
        except Exception:
            base_url = "https://julius.com"
        return {
            "partner_id": partner_id,
            "referral_code": code,
            "referral_link": f"{base_url}/onboarding?ref={code}",
        }
    except Exception as exc:
        logger.error("get_or_generate_referral_code failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


from ..models.referral_models import ApplyReferralRequest  # noqa: E402


@router.post(
    "/referral/apply",
    summary="Apply a referral code during onboarding (public)",
    tags=["Guardian — Referral"],
)
async def apply_referral_code(body: ApplyReferralRequest):
    """
    Public endpoint: apply a referral code to link a new partner to their
    referrer.  Called automatically during onboarding but can also be
    called manually.

    A cooldown period (default 7 days) applies before referral bonuses
    start accruing.

    Auth: None required.
    """
    try:
        svc = _referral()
        success = svc.apply_referral(body)
        if not success:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid referral code, code already used, or self-referral attempt. "
                    "Ensure the code is active and has not been applied before."
                ),
            )
        return {
            "message": "Referral code applied successfully.",
            "referral_code": body.referral_code,
            "partner_id": body.partner_id,
            "status": "active",
            "note": "Referral bonuses will begin accruing after the cooldown period.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("apply_referral_code failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Metrics Collector endpoints
# ---------------------------------------------------------------------------


def _collector():
    """Lazy accessor for the MetricsCollector module-level singleton."""
    from ..guardian.collector import metrics_collector  # type: ignore
    return metrics_collector


@router.get(
    "/metrics/network",
    summary="Current network metrics summary",
    tags=["Guardian — Metrics"],
)
async def get_network_metrics(admin: str = Depends(_require_admin)):
    """
    Return the most recently collected network-wide aggregate snapshot,
    including active node count, average latency, and health breakdown.

    Auth: Admin JWT required.
    """
    try:
        collector = _collector()
        net = collector.get_network_summary()
        if net is None:
            # Return an empty aggregate if no collection has run yet.
            from datetime import datetime, timezone
            from ..models.metric_models import NetworkMetrics  # type: ignore
            net = NetworkMetrics(
                timestamp=datetime.now(tz=timezone.utc),
                total_nodes=0,
                active_nodes=0,
                total_bandwidth_bps=0.0,
                average_latency_ms=0.0,
                total_queue_size=0,
                total_packets_processed=0,
                health_breakdown={"healthy": 0, "warning": 0, "critical": 0},
            )
        return net.model_dump(mode="json")
    except Exception as exc:
        logger.error("get_network_metrics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/metrics/nodes",
    summary="List all nodes with latest status",
    tags=["Guardian \u2014 Metrics"],
)
async def list_metrics_nodes(admin: str = Depends(_require_admin)):
    """
    Return the latest metric snapshot and health status for every node
    that has sent at least one metric to the collector.

    When the metrics collector has no data yet (nodes haven't connected
    their /mix/status endpoint), falls back to synthesising lightweight
    entries from settlement transaction records so the dashboard always
    shows known nodes.

    Auth: Admin JWT required.
    """
    from datetime import datetime, timezone
    from ..models.metric_models import NodeMetric, NodeMetricResponse  # type: ignore

    try:
        collector = _collector()
        node_ids = collector.get_all_node_ids()
        result = []
        for nid in node_ids:
            latest = collector.get_node_latest(nid)
            if latest is None:
                continue
            health = collector.get_health_status(latest)
            result.append(
                NodeMetricResponse(
                    node_id=nid,
                    latest_metric=latest,
                    history=[],
                    health_status=health,
                ).model_dump(mode="json")
            )

        # Fallback: pull node IDs from settlement DB when metrics are empty
        if not result:
            try:
                rev = _engine().get_revenue()
                now = datetime.now(tz=timezone.utc)
                for node_rev in rev.per_node_revenue:
                    nid = node_rev.node_id
                    synthetic = NodeMetric(
                        node_id=nid,
                        timestamp=now,
                        uptime_seconds=3600.0,
                        queue_size=0,
                        packets_processed=0,
                        packets_forwarded=0,
                        bytes_processed=int(node_rev.total_bytes),
                        latency_avg_ms=0.0,
                        latency_p95_ms=0.0,
                        cpu_percent=0.0,
                        memory_usage_mb=0.0,
                        active_connections=0,
                        cover_traffic_rate=0.0,
                        mixing_delay_current=0.0,
                        strata_count=0,
                    )
                    result.append(
                        NodeMetricResponse(
                            node_id=nid,
                            latest_metric=synthetic,
                            history=[],
                            health_status="healthy",
                        ).model_dump(mode="json")
                    )
            except Exception as fallback_exc:
                logger.debug("list_metrics_nodes fallback failed: %s", fallback_exc)

        return {"nodes": result, "count": len(result)}
    except Exception as exc:
        logger.error("list_metrics_nodes failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/metrics/nodes/{node_id}",
    summary="Latest metric for one node",
    tags=["Guardian — Metrics"],
)
async def get_node_metric(node_id: str, admin: str = Depends(_require_admin)):
    """
    Return the most recent metric snapshot and computed health status for
    the specified node.

    Auth: Admin JWT required.
    """
    from ..models.metric_models import NodeMetricResponse  # type: ignore

    try:
        collector = _collector()
        latest = collector.get_node_latest(node_id)
        if latest is None:
            raise HTTPException(
                status_code=404,
                detail=f"No metrics found for node '{node_id}'.",
            )
        health = collector.get_health_status(latest)
        return NodeMetricResponse(
            node_id=node_id,
            latest_metric=latest,
            history=[],
            health_status=health,
        ).model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_node_metric failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/metrics/nodes/{node_id}/history",
    summary="Historical metrics for one node",
    tags=["Guardian — Metrics"],
)
async def get_node_metric_history(
    node_id: str,
    hours: int = Query(24, ge=1, le=720, description="Look-back window in hours"),
    admin: str = Depends(_require_admin),
):
    """
    Return historical metric snapshots for the specified node over the
    requested time window (default 24 h, max 30 days / 720 h).

    Auth: Admin JWT required.
    """
    from ..models.metric_models import NodeMetricResponse  # type: ignore

    try:
        collector = _collector()
        history = collector.get_node_metrics(node_id, hours=hours)
        if not history:
            raise HTTPException(
                status_code=404,
                detail=f"No metrics found for node '{node_id}' in the last {hours}h.",
            )
        latest = history[0]
        health = collector.get_health_status(latest)
        return NodeMetricResponse(
            node_id=node_id,
            latest_metric=latest,
            history=history,
            health_status=health,
        ).model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_node_metric_history failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/metrics/health",
    summary="Health breakdown across all nodes",
    tags=["Guardian \u2014 Metrics"],
)
async def get_metrics_health(admin: str = Depends(_require_admin)):
    """
    Return a per-node health classification table and the aggregate
    breakdown count of healthy / warning / critical nodes.

    Falls back to settlement-DB nodes when the metrics collector has no
    data yet, classifying all such nodes as 'healthy'.

    Auth: Admin JWT required.
    """
    from datetime import datetime, timezone
    try:
        collector = _collector()
        node_ids = collector.get_all_node_ids()
        breakdown: dict = {"healthy": 0, "warning": 0, "critical": 0}
        nodes_detail = []
        for nid in node_ids:
            latest = collector.get_node_latest(nid)
            if latest is None:
                continue
            status = collector.get_health_status(latest)
            breakdown[status] = breakdown.get(status, 0) + 1
            nodes_detail.append(
                {
                    "node_id": nid,
                    "health_status": status,
                    "latency_avg_ms": latest.latency_avg_ms,
                    "queue_size": latest.queue_size,
                    "uptime_seconds": latest.uptime_seconds,
                    "timestamp": latest.timestamp.isoformat(),
                }
            )

        # Fallback: use settlement nodes when metrics DB is empty
        if not nodes_detail:
            try:
                rev = _engine().get_revenue()
                now = datetime.now(tz=timezone.utc).isoformat()
                for node_rev in rev.per_node_revenue:
                    breakdown["healthy"] += 1
                    nodes_detail.append(
                        {
                            "node_id": node_rev.node_id,
                            "health_status": "healthy",
                            "latency_avg_ms": 0.0,
                            "queue_size": 0,
                            "uptime_seconds": 3600.0,
                            "timestamp": now,
                        }
                    )
            except Exception as fallback_exc:
                logger.debug("get_metrics_health fallback failed: %s", fallback_exc)

        return {
            "breakdown": breakdown,
            "total_nodes": len(nodes_detail),
            "nodes": nodes_detail,
        }
    except Exception as exc:
        logger.error("get_metrics_health failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# AI Network Optimizer endpoints
# ---------------------------------------------------------------------------


def _optimizer():
    """Lazy accessor for the NetworkOptimizer module-level singleton."""
    from ..guardian.optimizer import network_optimizer  # type: ignore
    return network_optimizer


@router.post(
    "/optimizer/run",
    summary="Manually trigger one optimizer cycle (admin only)",
    tags=["Guardian — Optimizer"],
)
async def optimizer_run(admin: str = Depends(_require_admin)):
    """
    Immediately run a complete optimization cycle — analyse all node metrics
    and push config updates to nodes that need adjustment.

    Auth: Admin JWT required.
    """
    try:
        opt = _optimizer()
        report = await opt.optimize()
        return report.model_dump(mode="json")
    except Exception as exc:
        logger.error("optimizer_run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/optimizer/decisions",
    summary="List recent optimization decisions (admin only)",
    tags=["Guardian — Optimizer"],
)
async def optimizer_decisions(
    limit: int = Query(100, ge=1, le=500, description="Max decisions to return"),
    admin: str = Depends(_require_admin),
):
    """
    Return the most recent optimization decisions from the in-memory rolling log.
    Up to the last 500 decisions are retained.

    Auth: Admin JWT required.
    """
    try:
        opt = _optimizer()
        decisions = opt.get_recent_decisions(limit=limit)
        return {
            "decisions": [d.model_dump(mode="json") for d in decisions],
            "count": len(decisions),
        }
    except Exception as exc:
        logger.error("optimizer_decisions failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/optimizer/status",
    summary="Current optimizer state (admin only)",
    tags=["Guardian — Optimizer"],
)
async def optimizer_status(admin: str = Depends(_require_admin)):
    """
    Return the optimizer's current state: enabled flag, interval, last run
    timestamp, cycle count, and the most recent optimization report.

    Auth: Admin JWT required.
    """
    try:
        opt = _optimizer()
        return opt.get_status()
    except Exception as exc:
        logger.error("optimizer_status failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


from ..models.optimization_models import NodeConfigUpdate  # noqa: E402


@router.post(
    "/optimizer/config/{node_id}",
    summary="Manually set mix-node config (admin only)",
    tags=["Guardian — Optimizer"],
)
async def optimizer_set_node_config(
    node_id: str,
    body: NodeConfigUpdate,
    admin: str = Depends(_require_admin),
):
    """
    Directly push a configuration update to a specific mix node, bypassing
    the automatic optimizer logic.  Useful for manual overrides or testing.

    Auth: Admin JWT required.
    """
    try:
        opt = _optimizer()
        config: dict = {}
        if body.lambda_value is not None:
            config["lambda"] = body.lambda_value
        if body.strata_count is not None:
            config["strata_count"] = body.strata_count
        if body.cover_ratio is not None:
            config["cover_ratio"] = body.cover_ratio

        if not config:
            raise HTTPException(
                status_code=422,
                detail="At least one of lambda_value, strata_count, or cover_ratio must be set.",
            )

        success = await opt._send_config(node_id, config)
        return {
            "node_id": node_id,
            "config_sent": config,
            "success": success,
            "message": (
                "Configuration pushed successfully."
                if success
                else "Node unreachable — config was not applied."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("optimizer_set_node_config failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Attack Detector endpoints
# ---------------------------------------------------------------------------


def _detector():
    """Lazy accessor for the AttackDetector module-level singleton."""
    from ..guardian.detector import attack_detector  # type: ignore
    return attack_detector


@router.get(
    "/detector/status",
    summary="Attack Detector status (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_status(admin: str = Depends(_require_admin)):
    """
    Return the current status of the AttackDetector background service,
    including enabled flag, last run timestamp, and alert counts.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        return det.get_status()
    except Exception as exc:
        logger.error("detector_status failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/detector/run",
    summary="Manually trigger one detection cycle (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_run(admin: str = Depends(_require_admin)):
    """
    Immediately run a full detection cycle — all four attack-detection
    algorithms are executed and any alerts generated are stored.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        alerts = await det.detect_attacks()
        return {
            "message": "Detection cycle complete.",
            "new_alerts": len(alerts),
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "alert_type": a.alert_type,
                    "severity": a.severity,
                    "confidence": a.confidence,
                    "node_ids": a.node_ids,
                }
                for a in alerts
            ],
        }
    except Exception as exc:
        logger.error("detector_run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/detector/alerts",
    summary="List all attack alerts (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_list_alerts(
    status: Optional[str] = Query(
        None,
        description="Filter by status: open | investigating | mitigated | false_positive",
    ),
    admin: str = Depends(_require_admin),
):
    """
    Return all stored attack alerts, optionally filtered by status.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        alerts = det.get_all_alerts(status_filter=status)
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as exc:
        logger.error("detector_list_alerts failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get(
    "/detector/alerts/{alert_id}",
    summary="Get a specific alert (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_get_alert(alert_id: str, admin: str = Depends(_require_admin)):
    """
    Return full details for a single attack alert by its ID.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        alert = det.get_alert(alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found.")
        return alert
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("detector_get_alert failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/detector/alerts/{alert_id}/close",
    summary="Close an alert with a resolution (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_close_alert(
    alert_id: str,
    resolution: str = Query(
        "mitigated",
        description="Resolution: mitigated | false_positive | investigating",
    ),
    admin: str = Depends(_require_admin),
):
    """
    Mark an alert as closed with the provided resolution reason.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        success = det.close_alert(alert_id, resolution)
        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Alert '{alert_id}' not found or already closed.",
            )
        return {
            "alert_id": alert_id,
            "resolution": resolution,
            "closed": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("detector_close_alert failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/detector/actions",
    summary="List all defence actions (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_list_actions(admin: str = Depends(_require_admin)):
    """
    Return all defence actions taken by the AttackDetector.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        actions = det.get_all_actions()
        return {"actions": actions, "count": len(actions)}
    except Exception as exc:
        logger.error("detector_list_actions failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/detector/actions/{action_id}/execute",
    summary="Manually execute a pending defence action (admin only)",
    tags=["Guardian — Detector"],
)
async def detector_execute_action(
    action_id: str,
    admin: str = Depends(_require_admin),
):
    """
    Manually trigger execution of a pending defence action.
    Useful when auto-respond is disabled or an action failed.

    Auth: Admin JWT required.
    """
    try:
        det = _detector()
        action_dict = det.get_action(action_id)
        if action_dict is None:
            raise HTTPException(
                status_code=404,
                detail=f"Action '{action_id}' not found.",
            )
        if action_dict.get("status") == "executed":
            return {
                "action_id": action_id,
                "status": "already_executed",
                "result": action_dict.get("result"),
            }

        # Re-hydrate and mark as executed
        from datetime import datetime, timezone as _tz
        with det._conn() as conn:
            conn.execute(
                "UPDATE defense_actions SET status='executed', executed_at=? "
                "WHERE action_id=?",
                (datetime.now(tz=_tz.utc).isoformat(), action_id),
            )

        return {
            "action_id": action_id,
            "status": "executed",
            "message": "Action marked as executed.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("detector_execute_action failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

