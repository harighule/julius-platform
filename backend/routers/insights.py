"""
JULIUS Insights Router — Real analytics computed from actual database data.
"""

import logging
import json
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/insights", tags=["Insights & Analytics"])


class WorkflowRequest(BaseModel):
    name: str
    description: str = ""
    trigger_type: str = "manual"
    actions: Optional[list] = None


@router.get("/analytics")
async def get_analytics():
    """Real analytics computed from actual database data."""
    stats = db.get_system_stats()
    vulns = db.get_vulnerabilities(limit=500)
    scans = db.get_recent_scans(100)
    alerts = db.get_behavioral_alerts(200)
    event_stats = db.get_event_stats()
    patterns = db.get_behavioral_patterns()

    # Vulnerability severity breakdown (real)
    severity_counts = {}
    for v in vulns:
        s = v.get("severity", "info")
        severity_counts[s] = severity_counts.get(s, 0) + 1

    # Vulnerability by service (real)
    vuln_by_service = {}
    for v in vulns:
        svc = v.get("service", "unknown")
        vuln_by_service[svc] = vuln_by_service.get(svc, 0) + 1

    # Scan coverage (real)
    completed_scans = [s for s in scans if s.get("status") == "completed"]
    running_scans = [s for s in scans if s.get("status") == "running"]
    unique_targets = set(s.get("target", "") for s in scans)
    total_open_ports = 0
    for s in completed_scans:
        results = s.get("results", {})
        if isinstance(results, dict):
            ports = results.get("open_ports", [])
            if isinstance(ports, list):
                total_open_ports += len(ports)

    scan_coverage = {
        "total_scans": len(scans),
        "completed": len(completed_scans),
        "running": len(running_scans),
        "unique_targets": len(unique_targets),
        "total_open_ports": total_open_ports,
    }

    # Scan type breakdown
    scan_types = {}
    for s in scans:
        st = s.get("scan_type", "unknown")
        scan_types[st] = scan_types.get(st, 0) + 1

    # Alert severity breakdown (real)
    alert_severity = {}
    for a in alerts:
        s = a.get("severity", "unknown")
        alert_severity[s] = alert_severity.get(s, 0) + 1

    # Alert type breakdown
    alert_types = {}
    for a in alerts:
        t = a.get("alert_type", "unknown")
        alert_types[t] = alert_types.get(t, 0) + 1

    return {
        "overview": stats,
        "severity_counts": severity_counts,
        "vuln_by_service": vuln_by_service,
        "scan_coverage": scan_coverage,
        "scan_types": scan_types,
        "event_breakdown": event_stats.get("event_types", {}),
        "alert_severity": alert_severity,
        "alert_types": alert_types,
        "behavioral": {
            "active_patterns": len([p for p in patterns if p.get("is_active")]),
            "total_patterns": len(patterns),
            "total_alerts": len(alerts),
        },
        "total_vulns": len(vulns),
        "total_events": event_stats.get("total_events", 0),
    }


@router.get("/workflows")
async def list_workflows():
    workflows = db.get_workflows()
    return {"workflows": workflows, "total": len(workflows)}


@router.post("/workflows")
async def create_workflow(req: WorkflowRequest):
    result = db.add_workflow(req.name, req.description, req.trigger_type, req.actions)
    return result


@router.get("/dashboard")
async def dashboard_data():
    stats = db.get_system_stats()
    recent_events = db.get_recent_events(10)
    recent_scans = db.get_recent_scans(5)
    alerts = db.get_behavioral_alerts(5)

    return {
        "stats": stats,
        "recent_events": recent_events,
        "recent_scans": recent_scans,
        "recent_alerts": alerts,
        "total_scans": stats.get("total_scans", 0),
        "total_vulnerabilities": stats.get("total_vulnerabilities", 0),
        "total_events": stats.get("total_events", 0),
        "total_alerts": stats.get("total_alerts", 0),
    }
