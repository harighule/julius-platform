"""
CyberStrike Result Normalizer
Converts CyberStrike scan results into Julius DB format (scans, vulnerabilities, events, cognitive memory).
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("julius.cyberstrike.normalizer")


def _db():
    from ..database import db
    return db


def store_cyberstrike_scan(cs_result: dict) -> Optional[str]:
    """Normalize CyberStrike scan results into Julius DB."""
    try:
        target = cs_result.get("target", "unknown")
        vulns = cs_result.get("vulnerabilities", [])

        # Create scan record in Julius
        scan_id = _db().create_scan(
            scan_id=f"cs_{target.replace('.', '_')}",
            target=target,
            scan_type="cyberstrike_owasp",
        )

        # Store each vulnerability
        for vuln in vulns:
            _db().add_vulnerability(
                scan_id=scan_id,
                title=vuln.get("title", "Unknown"),
                severity=map_severity(vuln.get("cvss", 0)),
                host=target,
                port=vuln.get("port", 0),
                service=vuln.get("service", "web"),
                description=vuln.get("description", ""),
                cve_id=vuln.get("cwe", ""),
            )

        # Store in cognitive memory
        try:
            from .cognitive_memory import remember_fact
            fact = (
                f"CyberStrike found {len(vulns)} vulnerabilities on {target}: "
                + ", ".join(v.get("title", "?") for v in vulns[:5])
            )
            remember_fact(fact, category="vulnerability", confidence=0.95)
        except Exception:
            pass

        # Create event
        try:
            _db().create_event(
                event_type="cyberstrike_scan_complete",
                source="cyberstrike",
                data={
                    "scan_id": scan_id,
                    "target": target,
                    "vuln_count": len(vulns),
                    "critical": sum(1 for v in vulns if v.get("cvss", 0) >= 9.0),
                    "high": sum(1 for v in vulns if 7.0 <= v.get("cvss", 0) < 9.0),
                },
            )
        except Exception:
            pass

        return scan_id
    except Exception as e:
        logger.error(f"Failed to store CyberStrike scan: {e}")
        return None


def map_severity(cvss: float) -> str:
    if cvss >= 9.0:
        return "critical"
    if cvss >= 7.0:
        return "high"
    if cvss >= 4.0:
        return "medium"
    if cvss > 0:
        return "low"
    return "info"
