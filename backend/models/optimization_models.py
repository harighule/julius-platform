"""
JULIUS — Optimization Models
Pydantic models for the AI Network Optimizer: decisions, reports, and config updates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class OptimizationDecision(BaseModel):
    """A single optimization action proposed/applied for one node."""

    node_id: str = Field(..., description="Target mix node identifier")
    timestamp: datetime = Field(..., description="When this decision was made (UTC)")
    action_type: str = Field(
        ...,
        description=(
            "Type of adjustment: 'adjust_lambda' | 'adjust_strata' | "
            "'adjust_cover_rate' | 'reroute_traffic'"
        ),
    )
    previous_value: float = Field(..., description="Value before adjustment")
    new_value: float = Field(..., description="Proposed/applied value")
    reason: str = Field(..., description="Human-readable rationale for this decision")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (0-1) that this decision is appropriate",
    )
    metrics_used: Dict = Field(
        default_factory=dict,
        description="Snapshot of the metrics that triggered this decision",
    )
    applied: bool = Field(
        default=False,
        description="True when the decision was successfully pushed to the node",
    )


class OptimizationReport(BaseModel):
    """Summary of a complete optimization cycle."""

    timestamp: datetime = Field(..., description="When this optimization cycle ran (UTC)")
    decisions: List[OptimizationDecision] = Field(
        default_factory=list,
        description="All decisions proposed during this cycle",
    )
    summary: Dict = Field(
        default_factory=dict,
        description=(
            "High-level counts, e.g. "
            "{'lambda_adjustments': 5, 'strata_changes': 2, 'reroutes': 3}"
        ),
    )
    health_before: Dict = Field(
        default_factory=dict,
        description="Network health snapshot before optimizations were applied",
    )
    health_after: Dict = Field(
        default_factory=dict,
        description="Network health snapshot after optimizations were applied",
    )
    nodes_evaluated: int = Field(0, ge=0, description="Total nodes evaluated this cycle")
    decisions_applied: int = Field(0, ge=0, description="Decisions successfully sent to nodes")
    errors: List[str] = Field(
        default_factory=list,
        description="Any errors encountered during this cycle",
    )


class NodeConfigUpdate(BaseModel):
    """Request body for pushing a config change to a mix node."""

    node_id: str = Field(..., description="Target mix node identifier")
    lambda_value: Optional[float] = Field(
        None,
        gt=0.0,
        description="New Poisson mixing delay λ (seconds, > 0)",
    )
    strata_count: Optional[int] = Field(
        None,
        ge=1,
        description="New number of mixing strata (≥ 1)",
    )
    cover_ratio: Optional[float] = Field(
        None,
        ge=0.0,
        description="New cover-traffic ratio relative to real traffic (≥ 0)",
    )


class OptimizerStatus(BaseModel):
    """Current state of the background optimizer."""

    enabled: bool = Field(..., description="Whether the optimizer is active")
    interval_seconds: int = Field(..., description="How often the optimizer runs (s)")
    last_run: Optional[datetime] = Field(None, description="Timestamp of the last cycle")
    last_report: Optional[OptimizationReport] = Field(
        None, description="Most recent optimization report"
    )
    total_cycles: int = Field(0, ge=0, description="Number of complete optimizer cycles so far")
    total_decisions_applied: int = Field(
        0, ge=0, description="Cumulative count of successfully applied decisions"
    )
