"""
JULIUS — Alert & Defense Action Models
=======================================
Pydantic data models used by the Attack Detector, Guardian API, and Pantheon
audit log for structured representation of security alerts and defensive
responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AttackAlert(BaseModel):
    """Represents a detected attack or suspicious activity."""

    alert_id: str
    alert_type: str  # "timing_attack" | "sybil_attack" | "intersection_attack" | "node_compromise"
    severity: str    # "low" | "medium" | "high" | "critical"
    timestamp: datetime
    node_ids: List[str]          # affected node IDs
    description: str
    evidence: Dict               # raw data that triggered the alert
    confidence: float            # 0-1 confidence score
    status: str = "open"        # "open" | "investigating" | "mitigated" | "false_positive"
    auto_response: Optional[str] = None  # "rotation" | "blacklist" | "escalate"


class DefenseAction(BaseModel):
    """A defensive action taken in response to an alert."""

    action_id: str
    alert_id: str
    action_type: str             # "rotate_circuits" | "blacklist_node" | "increase_mixing" | "escalate_human"
    target_node: Optional[str] = None
    status: str = "pending"     # "pending" | "executed" | "failed"
    executed_at: Optional[datetime] = None
    result: Optional[str] = None


class DetectorStatus(BaseModel):
    """Current status of the AttackDetector background service."""

    enabled: bool
    running: bool
    last_run: Optional[datetime]
    total_alerts: int
    open_alerts: int
    mitigated_alerts: int
