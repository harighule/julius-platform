"""
JULIUS — Revenue API Models
Pydantic schemas for the dashboard revenue endpoints exposed via
GET /guardian/revenue/summary, /trend, /nodes, and /transactions.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Revenue summary (GET /guardian/revenue/summary)
# ---------------------------------------------------------------------------


class RevenueSummary(BaseModel):
    """Overall platform revenue summary returned by the summary endpoint."""

    total_revenue: float = Field(0.0, description="All-time commission total in USD.")
    revenue_today: float = Field(0.0, description="Commission earned today (UTC).")
    revenue_this_week: float = Field(
        0.0, description="Commission earned this calendar week (Mon–Sun)."
    )
    revenue_this_month: float = Field(
        0.0, description="Commission earned this calendar month."
    )
    average_daily_revenue: float = Field(
        0.0, description="Mean daily revenue over the last 30 days."
    )
    node_count: int = Field(0, description="Total number of nodes with any revenue.")
    active_nodes: int = Field(
        0, description="Nodes with revenue recorded today."
    )


# ---------------------------------------------------------------------------
# Daily trend point (GET /guardian/revenue/trend)
# ---------------------------------------------------------------------------


class RevenueTrendPoint(BaseModel):
    """One data-point in the 30-day daily revenue trend series."""

    date: str = Field(..., description="Calendar date in YYYY-MM-DD format.")
    revenue: float = Field(0.0, description="Total commission for this day in USD.")
    transactions: int = Field(0, description="Number of transactions on this day.")


# ---------------------------------------------------------------------------
# Per-node revenue (GET /guardian/revenue/nodes)
# ---------------------------------------------------------------------------


class NodeRevenue(BaseModel):
    """Revenue breakdown for a single mix-node operator."""

    node_id: str = Field(..., description="Unique mix-node identifier.")
    partner_id: Optional[str] = Field(None, description="Affiliated partner ID.")
    total_bytes: int = Field(0, ge=0, description="Total bytes routed by this node.")
    total_commission: float = Field(
        0.0, ge=0.0, description="Gross commission earned in USD."
    )
    revenue_share_pct: float = Field(
        30.0, ge=0.0, le=100.0,
        description="Percentage of commission paid to the partner operator.",
    )
    payout_amount: float = Field(
        0.0, ge=0.0, description="Net USD owed to the partner (after revenue share)."
    )
