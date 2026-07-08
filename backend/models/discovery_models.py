"""
JULIUS — Discovery Models
Pydantic schemas for the passive dark-web node discovery subsystem.

Entity types
------------
    DiscoveredNode   — a single Tor/I2P/Mixnet relay found via public sources
    DiscoveryRun     — metadata about a single execution of DiscoveryEngine
    DiscoveryStatus  — lightweight status snapshot returned by API
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field
from pydantic import ConfigDict
from pydantic.functional_serializers import field_serializer


# ---------------------------------------------------------------------------
# Core node record
# ---------------------------------------------------------------------------


class DiscoveredNode(BaseModel):
    """A single relay / router discovered from a public data source."""

    node_id: str = Field(..., description="Unique identifier (fingerprint or derived hash).")
    ip_address: Optional[str] = Field(None, description="IPv4 or IPv6 address if publicly known.")
    public_key: Optional[str] = Field(None, description="Relay public key or fingerprint hex.")
    software: Optional[str] = Field(None, description="Software name, e.g. 'tor', 'i2pd', 'nym'.")
    version: Optional[str] = Field(None, description="Software version string.")
    network: str = Field(..., description="Network type: 'tor', 'i2p', or 'mixnet'.")
    uptime_seconds: Optional[int] = Field(None, ge=0, description="Observed uptime in seconds.")
    bandwidth_mbps: Optional[float] = Field(None, ge=0.0, description="Advertised or estimated bandwidth in Mbps.")
    location: Optional[str] = Field(None, description="Country code or city string if available.")
    discovered_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of discovery.")
    source: str = Field(..., description="Source module that produced this record, e.g. 'tor_metrics'.")
    score: float = Field(0.0, ge=0.0, le=100.0, description="Composite quality score 0–100.")

    # Extended metadata (optional, populated when available)
    or_port: Optional[int] = Field(None, description="ORPort (Tor) or router port.")
    dir_port: Optional[int] = Field(None, description="DirPort for Tor directory queries.")
    flags: Optional[List[str]] = Field(default_factory=list, description="Relay flags, e.g. ['Guard', 'Exit'].")
    contact: Optional[str] = Field(None, description="Operator contact string (publicly advertised).")

    model_config = ConfigDict()


# ---------------------------------------------------------------------------
# Discovery run record
# ---------------------------------------------------------------------------


class DiscoveryRun(BaseModel):
    """Metadata about a single end-to-end execution of DiscoveryEngine."""

    run_id: str = Field(..., description="UUID of the discovery run.")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    nodes_discovered: int = Field(0, ge=0)
    nodes_updated: int = Field(0, ge=0)
    nodes_new: int = Field(0, ge=0)
    errors: List[str] = Field(default_factory=list)
    sources_used: List[str] = Field(default_factory=list)
    status: str = Field("running", description="'running' | 'completed' | 'failed'")

    model_config = ConfigDict()


# ---------------------------------------------------------------------------
# API status snapshot
# ---------------------------------------------------------------------------


class DiscoveryStatus(BaseModel):
    """Lightweight status object returned by GET /guardian/discovery/nodes."""

    enabled: bool
    total_nodes: int = 0
    last_run_at: Optional[datetime] = None
    last_run_nodes_discovered: int = 0
    sources_configured: List[str] = Field(default_factory=list)
    discovery_interval_seconds: int = 86400

    model_config = ConfigDict()
