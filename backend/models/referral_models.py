"""
JULIUS — Referral System Models
Pydantic schemas for the viral referral system: referral codes,
partner earnings, multi-level trees, and global analytics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ReferredPartner(BaseModel):
    """Stats for a single partner that was referred by someone."""

    partner_id: str = Field(..., description="Partner ID of the referred partner")
    node_id: Optional[str] = Field(None, description="Node ID if registered")
    joined_at: datetime = Field(..., description="When this partner onboarded")
    status: str = Field(
        ..., description="One of: active | pending | decommissioned"
    )
    total_bytes_routed: int = Field(0, ge=0, description="Total bytes routed by referred node")
    total_commission_earned: float = Field(
        0.0, ge=0.0, description="Total commission earned by referred node"
    )
    your_bonus_earned: float = Field(
        0.0, ge=0.0, description="Total referral bonus paid to the referrer from this partner"
    )


class TopReferrer(BaseModel):
    """Summary of a top-performing referrer for analytics."""

    partner_id: str
    referral_code: str
    total_referred: int = 0
    active_referred: int = 0
    total_bonus_earned: float = 0.0


# ---------------------------------------------------------------------------
# Core referral models
# ---------------------------------------------------------------------------


class ReferralInfo(BaseModel):
    """Full referral profile for a partner."""

    partner_id: str
    referral_code: str
    referral_link: str = Field(
        ..., description="e.g., 'https://julius.com/onboarding?ref=JULIUS-ABC123XY'"
    )
    referred_partners: List[ReferredPartner] = Field(default_factory=list)
    total_referred: int = Field(0, ge=0)
    total_referral_earnings: float = Field(
        0.0, ge=0.0, description="Earnings from currently active referrals"
    )
    lifetime_referral_earnings: float = Field(
        0.0, ge=0.0, description="All-time referral bonus earned"
    )


class ReferralTree(BaseModel):
    """Multi-level referral tree up to max_levels deep."""

    root: str = Field(..., description="Root partner_id")
    depth: int = Field(..., ge=0, description="Actual depth of the tree")
    tree: Dict = Field(
        default_factory=dict,
        description="Nested dict: {partner_id: {node_id, status, children: {...}}}",
    )


# ---------------------------------------------------------------------------
# Request / action models
# ---------------------------------------------------------------------------


class ApplyReferralRequest(BaseModel):
    """Request body to apply a referral code during onboarding."""

    referral_code: str = Field(..., description="The referral code to apply")
    partner_id: str = Field(..., description="The new partner being onboarded")


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class ReferralAnalytics(BaseModel):
    """Platform-wide referral analytics (admin endpoint)."""

    total_referrals_created: int = 0
    active_referrals: int = 0
    pending_referrals: int = 0
    total_referral_bonus_paid: float = 0.0
    top_referrers: List[TopReferrer] = Field(default_factory=list)
    referral_bonus_percent: float = Field(
        0.05, description="Current global referral bonus rate"
    )
    max_levels: int = Field(3, description="Max depth of multi-level referral bonuses")


# ---------------------------------------------------------------------------
# Response envelope for earnings
# ---------------------------------------------------------------------------


class ReferralEarningsResponse(BaseModel):
    """Earnings summary for a partner's referral activity."""

    partner_id: str
    referral_code: str
    total_referred: int = 0
    active_referred: int = 0
    total_bonus_earned: float = 0.0
    lifetime_bonus_earned: float = 0.0
    pending_cooldown: int = Field(
        0, description="Referrals still in cooldown period"
    )
    payments: List[Dict] = Field(
        default_factory=list,
        description="List of individual referral payment records",
    )
