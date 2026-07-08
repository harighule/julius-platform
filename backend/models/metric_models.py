"""
JULIUS — Metrics Models
Pydantic models for node-level and network-level performance metrics
used by the Metrics Collector and Guardian API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NodeMetric(BaseModel):
    """A single snapshot of performance/health data for one mix node."""

    node_id: str = Field(..., description="Unique identifier for the mix node")
    timestamp: datetime = Field(..., description="When this snapshot was captured (UTC)")

    # ── Uptime / Availability ───────────────────────────────────────────────
    uptime_seconds: float = Field(0.0, ge=0.0, description="Seconds since node startup")

    # ── Traffic ────────────────────────────────────────────────────────────
    queue_size: int = Field(0, ge=0, description="Current in-memory packet queue depth")
    packets_processed: int = Field(0, ge=0, description="Total packets processed since startup")
    packets_forwarded: int = Field(0, ge=0, description="Total packets forwarded to next hop")
    bytes_processed: int = Field(0, ge=0, description="Total bytes processed since startup")

    # ── Latency ────────────────────────────────────────────────────────────
    latency_avg_ms: float = Field(0.0, ge=0.0, description="Moving-average latency (ms)")
    latency_p95_ms: float = Field(0.0, ge=0.0, description="95th-percentile latency (ms)")

    # ── System Resources ───────────────────────────────────────────────────
    cpu_percent: float = Field(0.0, ge=0.0, le=100.0, description="CPU utilisation (%)")
    memory_usage_mb: float = Field(0.0, ge=0.0, description="RSS memory usage (MB)")

    # ── Connections ────────────────────────────────────────────────────────
    active_connections: int = Field(0, ge=0, description="Number of open sessions")

    # ── Mix-Network specifics ──────────────────────────────────────────────
    cover_traffic_rate: float = Field(
        0.0, ge=0.0, description="Cover-traffic emission rate (packets/second)"
    )
    mixing_delay_current: float = Field(
        0.0, ge=0.0, description="Current Poisson mixing delay λ (seconds)"
    )
    strata_count: int = Field(
        0, ge=0, description="Number of mixing strata this node participates in"
    )


class NodeMetricResponse(BaseModel):
    """Full response for a single node — latest snapshot plus history."""

    node_id: str
    latest_metric: NodeMetric
    history: List[NodeMetric] = Field(
        default_factory=list, description="Historical snapshots (newest first)"
    )
    health_status: str = Field(
        ..., description="Computed health label: 'healthy' | 'warning' | 'critical'"
    )


class NetworkMetrics(BaseModel):
    """Aggregate snapshot for the entire active node network."""

    timestamp: datetime = Field(..., description="When this aggregate was computed (UTC)")

    total_nodes: int = Field(0, ge=0, description="Nodes in the registry")
    active_nodes: int = Field(0, ge=0, description="Nodes successfully contacted this cycle")

    total_bandwidth_bps: float = Field(
        0.0, ge=0.0, description="Combined throughput estimate (bytes/s)"
    )
    average_latency_ms: float = Field(
        0.0, ge=0.0, description="Average latency across all active nodes (ms)"
    )
    total_queue_size: int = Field(0, ge=0, description="Sum of all node queue depths")
    total_packets_processed: int = Field(
        0, ge=0, description="Sum of packets_processed across all nodes"
    )

    health_breakdown: Dict[str, int] = Field(
        default_factory=lambda: {"healthy": 0, "warning": 0, "critical": 0},
        description="Count of nodes in each health category",
    )
