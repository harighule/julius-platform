"""
JULIUS — Settlement Models
Pydantic schemas for the Settlement Engine: transactions, batches,
node settlements, and revenue analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Core transaction record
# ---------------------------------------------------------------------------

class Transaction(BaseModel):
    """A single routed-packet billing event."""

    id: str = Field(..., description="Unique transaction UUID.")
    timestamp: datetime = Field(..., description="UTC time the packet was processed.")
    node_id: str = Field(..., description="Mix-node that routed the packet.")
    partner_id: Optional[str] = Field(None, description="Affiliated partner/operator ID.")
    token_serial_hash: str = Field(
        ...,
        description="SHA-256 of the bandwidth-token serial (privacy-preserving).",
    )
    bytes_routed: int = Field(..., ge=0, description="Payload bytes forwarded in this hop.")
    commission_earned: float = Field(..., ge=0.0, description="Commission in USD for this hop.")
    source_entity: Optional[str] = Field(None, description="Originating entity label.")
    destination_entity: Optional[str] = Field(None, description="Destination entity label.")
    settled: bool = Field(False, description="True once included in a processed batch.")


# ---------------------------------------------------------------------------
# Per-node aggregation
# ---------------------------------------------------------------------------

class NodeSettlement(BaseModel):
    """Revenue breakdown for a single node within a batch."""

    node_id: str
    partner_id: Optional[str] = None
    total_bytes: int = Field(..., ge=0)
    total_commission: float = Field(..., ge=0.0)
    revenue_share_pct: float = Field(
        30.0, ge=0.0, le=100.0, description="Percentage of commission paid to the partner."
    )
    payout_amount: float = Field(..., ge=0.0, description="USD owed to the partner operator.")
    status: str = Field(
        "pending", description="One of: pending | paid | failed | below_minimum"
    )


# ---------------------------------------------------------------------------
# Settlement batch
# ---------------------------------------------------------------------------

class SettlementBatch(BaseModel):
    """Aggregated settlement record covering a fixed time window."""

    batch_id: str
    start_time: datetime
    end_time: datetime
    total_transactions: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)
    total_commission: float = Field(..., ge=0.0)
    per_node_summary: Dict[str, NodeSettlement] = Field(
        default_factory=dict,
        description="Keyed by node_id.",
    )


# ---------------------------------------------------------------------------
# Revenue analytics
# ---------------------------------------------------------------------------

class NodeRevenue(BaseModel):
    """Revenue summary for a single node (used in /guardian/revenue/nodes)."""

    node_id: str
    partner_id: Optional[str] = None
    total_bytes: int = 0
    total_commission: float = 0.0
    payout_amount: float = 0.0
    transaction_count: int = 0


class DailyRevenue(BaseModel):
    """Aggregated revenue for a single calendar day."""

    date: str = Field(..., description="ISO-8601 date string, e.g. '2026-06-19'.")
    total_commission: float = 0.0
    total_bytes: int = 0
    transaction_count: int = 0


class RevenueResponse(BaseModel):
    """Top-level response for GET /guardian/revenue."""

    total_revenue: float = 0.0
    revenue_today: float = 0.0
    revenue_this_week: float = 0.0
    revenue_this_month: float = 0.0
    per_node_revenue: List[NodeRevenue] = Field(default_factory=list)
    revenue_trend: List[DailyRevenue] = Field(
        default_factory=list,
        description="Daily totals for the last 30 days.",
    )


# ---------------------------------------------------------------------------
# Payout instruction
# ---------------------------------------------------------------------------

class PayoutInstruction(BaseModel):
    """Payment instruction produced for an external payment processor."""

    payout_id: str
    node_id: str
    partner_id: Optional[str] = None
    amount_usd: float
    currency: str = "USD"
    prepared_at: datetime
    status: str = "prepared"
    memo: str = ""
