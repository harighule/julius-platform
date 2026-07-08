"""
JULIUS — Partner Onboarding Models
Pydantic models for partner/node-operator onboarding,
status tracking, install script generation, and referral system.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------


class PartnerOnboardRequest(BaseModel):
    """Request body to initiate partner onboarding."""

    node_ip: str = Field(..., description="Public IP address of the partner node")
    ssh_port: int = Field(22, description="SSH port on the partner node")
    ssh_username: str = Field("root", description="SSH username for installation")
    ssh_password: Optional[str] = Field(None, description="SSH password (optional)")
    ssh_key: Optional[str] = Field(
        None, description="Base64-encoded SSH private key (optional)"
    )
    referral_code: Optional[str] = Field(
        None, description="Referral code from an existing partner"
    )
    node_name: Optional[str] = Field(
        None, description="Human-readable name for the node"
    )
    contact_info: Optional[str] = Field(
        None,
        description="Encrypted email or session token for contact (optional)",
    )


class NodeRegisterRequest(BaseModel):
    """Called by the install script after successful VEIL installation."""

    partner_id: str = Field(..., description="Partner ID assigned during onboarding")
    public_key: str = Field(..., description="Node's Ed25519 public key (hex)")
    node_metadata: Optional[dict] = Field(
        default_factory=dict,
        description="Additional metadata: OS, Docker version, bandwidth, etc.",
    )


class DecommissionRequest(BaseModel):
    """Request to deactivate a partner node."""

    partner_id: str = Field(..., description="Partner ID to decommission")
    reason: Optional[str] = Field(None, description="Reason for decommissioning")


# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------


class PartnerStatusResponse(BaseModel):
    """Full status of a registered partner / node operator."""

    partner_id: str
    node_id: Optional[str] = None
    node_ip: str
    node_name: Optional[str] = None
    status: str  # pending | installing | active | failed | decommissioned
    joined_at: datetime
    last_heartbeat: Optional[datetime] = None
    revenue_share_percent: float = 0.30
    total_bytes_routed: int = 0
    total_commission_earned: float = 0.0
    referral_code: str
    referred_by: Optional[str] = None
    install_attempts: int = 0
    public_key: Optional[str] = None


class InstallScriptResponse(BaseModel):
    """Response containing the one-liner install script for a partner."""

    partner_id: str
    script: str  # full bash script
    one_liner: str  # curl | bash one-liner
    instructions: str  # plain-text step-by-step
    verification_command: str  # command to verify installation succeeded
    referral_code: str


class ReferralInfoResponse(BaseModel):
    """Referral link and code details for a partner."""

    partner_id: str
    referral_code: str
    referral_link: str
    referred_partners: list = Field(default_factory=list)
    total_referrals: int = 0
    referral_bonus_percent: float = 0.05
