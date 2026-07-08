"""
JULIUS Behavioral Router — Pattern detection, alerts, predictions.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/behavioral", tags=["Behavioral Analytics"])


class PatternRequest(BaseModel):
    name: str
    pattern_type: str = "behavioral"
    description: str = ""
    rules: Optional[dict] = None
    severity: str = "medium"


class AlertRequest(BaseModel):
    pattern_id: Optional[int] = None
    alert_type: str
    severity: str = "medium"
    message: str
    data: Optional[dict] = None


@router.get("/patterns")
async def list_patterns():
    """List all behavioral detection patterns."""
    patterns = db.get_behavioral_patterns()
    return {"patterns": patterns, "total": len(patterns)}


@router.post("/patterns")
async def create_pattern(req: PatternRequest):
    """Create a new behavioral pattern."""
    result = db.add_behavioral_pattern(
        name=req.name, pattern_type=req.pattern_type,
        description=req.description, rules=req.rules, severity=req.severity
    )
    db.add_event(
        event_id=f"evt_pattern_{result['id']}",
        event_type="pattern_created",
        source="julius-behavioral",
        data={"pattern_id": result["id"], "name": req.name}
    )
    return result


@router.put("/patterns/{pattern_id}")
async def update_pattern(pattern_id: int, req: PatternRequest):
    db.update_behavioral_pattern(pattern_id, req.model_dump(exclude_unset=True))
    return {"status": "updated", "pattern_id": pattern_id}


@router.delete("/patterns/{pattern_id}")
async def delete_pattern(pattern_id: int):
    db.delete_behavioral_pattern(pattern_id)
    return {"status": "deleted", "pattern_id": pattern_id}


@router.get("/alerts")
async def list_alerts(limit: int = 50, severity: Optional[str] = None):
    """List behavioral alerts."""
    alerts = db.get_behavioral_alerts(limit)
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/alerts")
async def create_alert(req: AlertRequest):
    """Create a behavioral alert."""
    alert_id = db.add_behavioral_alert(
        pattern_id=req.pattern_id, alert_type=req.alert_type,
        severity=req.severity, message=req.message, data=req.data
    )
    db.add_event(
        event_id=f"evt_alert_{alert_id}",
        event_type="behavioral_alert",
        source="julius-behavioral",
        data={"alert_id": alert_id, "severity": req.severity, "message": req.message}
    )
    return {"alert_id": alert_id, "status": "created"}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int):
    db.delete_behavioral_alert(alert_id)
    return {"status": "deleted", "alert_id": alert_id}


@router.get("/stats")
async def behavioral_stats():
    """Get behavioral engine statistics."""
    patterns = db.get_behavioral_patterns()
    alerts = db.get_behavioral_alerts(100)
    severity_counts = {}
    for a in alerts:
        s = a.get("severity", "unknown")
        severity_counts[s] = severity_counts.get(s, 0) + 1
    return {
        "total_patterns": len(patterns),
        "active_patterns": len([p for p in patterns if p.get("is_active")]),
        "total_alerts": len(alerts),
        "severity_distribution": severity_counts,
        "status": "operational",
    }
