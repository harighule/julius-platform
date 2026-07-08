"""
JULIUS Scanner Router — Network scanning, port scanning, vulnerability detection.
Real TCP connectivity checks, banner grabbing, service detection.
AXIOM + Causal Functor pipeline runs automatically after every scan.

VEIL Integration: Adds anonymized scanning via Tor + optional post-quantum routing.
"""

import logging
import socket
import asyncio
import uuid
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from ..database import db

# VEIL Integration - Anonymous Transport
from ..services.veil import get_veil_transport, RevenueEngine, AnonymityLevel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scanner", tags=["Scanner"])

# VEIL Global Instances
_veil_transport = None
_revenue_engine = RevenueEngine()


def _get_veil_transport():
    """Get or create VEIL transport instance."""
    global _veil_transport
    if _veil_transport is None:
        _veil_transport = get_veil_transport()
    return _veil_transport


# ── Well-known port/service mapping ───────────────────────────────────────
WELL_KNOWN = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc",
    139: "netbios-ssn", 143: "imap", 443: "https", 445: "microsoft-ds",
    993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle",
    3306: "mysql", 3389: "ms-wbt-server", 5432: "postgresql",
    5900: "vnc", 6379: "redis", 8080: "http-proxy", 8443: "https-alt",
    8888: "http-alt", 9090: "webmin", 27017: "mongodb",
}

TOP_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445,
    993, 995, 1433, 1521, 3306, 3389, 5432, 5900, 5985, 6379,
    8080, 8443, 8888, 9090, 27017,
]

VULN_SIGNATURES = {
    "ftp": [
        {"pattern": "220", "severity": "info", "title": "FTP Service Detected", "description": "FTP server is running"},
        {"pattern": "vsFTPd 2.3.4", "severity": "critical", "title": "vsFTPd 2.3.4 Backdoor (CVE-2011-2523)", "cve": "CVE-2011-2523"},
    ],
    "ssh": [
        {"pattern": "SSH-", "severity": "info", "title": "SSH Service Detected"},
        {"pattern": "OpenSSH_7.2", "severity": "high", "title": "OpenSSH 7.2 User Enumeration (CVE-2016-6210)", "cve": "CVE-2016-6210"},
    ],
    "http": [
        {"pattern": "Apache/2.4.49", "severity": "critical", "title": "Apache 2.4.49 Path Traversal (CVE-2021-41773)", "cve": "CVE-2021-41773"},
        {"pattern": "nginx", "severity": "info", "title": "Nginx Web Server Detected"},
    ],
    "smtp": [
        {"pattern": "220", "severity": "info", "title": "SMTP Service Detected"},
    ],
}

# ── Request Models ────────────────────────────────────────────────────────
class ScanRequest(BaseModel):
    target: str
    scan_type: str = "quick"  # quick, full, stealth
    ports: Optional[List[int]] = None
    timeout: float = 2.0


class PortCheckRequest(BaseModel):
    ip: str
    port: int
    timeout: float = 2.0


class AnonymizedScanRequest(BaseModel):
    """VEIL Anonymized Scan Request - uses Tor/mixnet for anonymity"""
    target: str
    scan_type: str = "quick"
    ports: Optional[List[int]] = None
    timeout: float = 10.0  # Higher timeout for Tor latency
    complexity: float = 1.0  # For revenue scaling
    anonymity_level: str = "tor_only"  # tor_only, mixnet, prism_sphinx


# ── Port scanning logic (Original - Preserved) ────────────────────────────
def _grab_banner(ip: str, port: int, timeout: float = 2.0) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
            if port in (80, 8080, 8443, 443, 8000, 8888):
                s.send(b"HEAD / HTTP/1.0\r\nHost: target\r\n\r\n")
            elif port == 25:
                pass
            else:
                s.send(b"\r\n")
            banner = s.recv(1024).decode("utf-8", errors="ignore").strip()
            return banner[:256]
    except Exception:
        return ""


def _check_port(ip: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((ip, port))
            if result == 0:
                service = WELL_KNOWN.get(port, "unknown")
                banner = _grab_banner(ip, port, timeout)
                return {"port": port, "status": "open", "service": service, "banner": banner}
            return {"port": port, "status": "closed", "service": "", "banner": ""}
    except socket.timeout:
        return {"port": port, "status": "filtered", "service": "", "banner": ""}
    except Exception as e:
        return {"port": port, "status": "error", "service": "", "banner": str(e)}


def _check_port_anonymized(ip: str, port: int, timeout: float = 10.0) -> Dict[str, Any]:
    """Check port using VEIL anonymous transport."""
    transport = _get_veil_transport()
    try:
        # Attempt connection through Tor/VEIL
        transport.route_request(f"http://{ip}:{port}", timeout=timeout)
        service = WELL_KNOWN.get(port, "unknown")
        return {"port": port, "status": "open", "service": service, "banner": ""}
    except Exception:
        return {"port": port, "status": "closed", "service": "", "banner": ""}


def _detect_vulnerabilities(scan_id: str, host: str, open_ports: List[Dict]) -> List[Dict]:
    vulns = []
    for port_info in open_ports:
        if port_info["status"] != "open":
            continue
        service = port_info["service"]
        banner = port_info.get("banner", "")
        sigs = VULN_SIGNATURES.get(service, [])
        for sig in sigs:
            if sig["pattern"].lower() in banner.lower() or sig["severity"] == "info":
                vuln = {
                    "host": host,
                    "port": port_info["port"],
                    "service": service,
                    "severity": sig["severity"],
                    "title": sig.get("title", "Unknown"),
                    "description": sig.get("description", ""),
                    "cve_id": sig.get("cve"),
                    "banner": banner,
                }
                vulns.append(vuln)
                db.add_vulnerability(
                    scan_id=scan_id,
                    host=host,
                    port=port_info["port"],
                    service=service,
                    severity=sig["severity"],
                    title=sig.get("title", "Unknown"),
                    description=sig.get("description", f"Banner: {banner}"),
                    cve_id=sig.get("cve"),
                )
    return vulns


# ── AXIOM + Causal Functor pipeline (called after scan completes) ─────────

def _run_axiom_pipeline(scan_id: str, target: str, open_ports: List[Dict], vulns: List[Dict]):
    """
    Synchronous wrapper that runs the AXIOM intelligence pipeline on
    completed scan results and stores the enriched report in the DB.
    Non-blocking — called in a background thread, failures are logged only.
    """
    try:
        scan_payload = [{
            "target": target,
            "ports": [p["port"] for p in open_ports],
            "vulnerabilities": [v.get("cve_id") or v.get("title") for v in vulns],
            "services": {str(p["port"]): p["service"] for p in open_ports},
            "risk_score": _compute_risk_score(vulns),
            "open_ports_count": len(open_ports),
        }]

        # Run async pipeline in a new event loop (we're in a thread)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from ..integration.pipeline import run_intelligence_pipeline
            pipeline_result = loop.run_until_complete(
                run_intelligence_pipeline(
                    scan_results=scan_payload,
                    target=target,
                    depth="standard",
                )
            )
        finally:
            loop.close()

        # Persist enriched result alongside the scan
        db.add_event(
            event_id=f"evt_axiom_{scan_id}",
            event_type="axiom_analysis_completed",
            source="julius-axiom-pipeline",
            data={
                "scan_id": scan_id,
                "target": target,
                "severity_breakdown": pipeline_result.get("summary", {}).get("severity_breakdown", {}),
                "recommendation": pipeline_result.get("summary", {}).get("recommendation", ""),
                "causal_paths": pipeline_result.get("summary", {}).get("causal_paths_found", 0),
                "axiom_findings_count": len(pipeline_result.get("axiom_findings", [])),
            }
        )

        # Update scan record with axiom enrichment
        conn = db._connect()
        try:
            import json
            conn.execute(
                "UPDATE scans SET axiom_analysis = ? WHERE id = ?",
                (json.dumps(pipeline_result), scan_id)
            )
            conn.commit()
        except Exception:
            # Column may not exist yet — non-fatal
            pass
        finally:
            conn.close()

        recommendation = pipeline_result.get("summary", {}).get("recommendation", "")
        logger.info("AXIOM pipeline completed for scan %s — %s", scan_id, recommendation)

    except Exception as e:
        logger.warning("AXIOM pipeline skipped for scan %s: %s", scan_id, e)


def _compute_risk_score(vulns: List[Dict]) -> float:
    """Simple risk score from vulnerability severities."""
    score = 0.0
    weights = {"critical": 9.0, "high": 7.0, "medium": 4.0, "low": 1.0, "info": 0.0}
    for v in vulns:
        score += weights.get(v.get("severity", "info"), 0.0)
    return min(score, 10.0)


# ── Background scan tasks ─────────────────────────────────────────────────

def _run_scan_task(scan_id: str, target: str, ports: List[int], timeout: float):
    """Background scan task — runs scan then triggers AXIOM pipeline."""
    try:
        open_ports = []
        all_results = []
        for port in ports:
            result = _check_port(target, port, timeout)
            all_results.append(result)
            if result["status"] == "open":
                open_ports.append(result)

        vulns = _detect_vulnerabilities(scan_id, target, open_ports)

        db.add_event(
            event_id=f"evt_scan_{scan_id}",
            event_type="scan_completed",
            source="julius-scanner",
            data={
                "scan_id": scan_id,
                "target": target,
                "open_ports": len(open_ports),
                "vulns": len(vulns),
            }
        )

        scan_results = {
            "target": target,
            "total_ports_scanned": len(ports),
            "open_ports": open_ports,
            "vulnerabilities": vulns,
            "vulnerability_count": len(vulns),
        }
        db.update_scan(scan_id, "completed", scan_results)

        # ── Auto-create identity profile ──────────────────────────────────
        try:
            existing = db.get_identities()
            handles = [i.get("handle") for i in existing]
            if target not in handles:
                identity_id = f"id-{uuid.uuid4().hex[:6]}"
                conn = db._connect()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO identities "
                        "(id, name, platform, handle, email, phone, created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (identity_id, f"Host_{target}", "network_scan", target,
                         None, None, datetime.utcnow().isoformat()),
                    )
                    conn.commit()
                finally:
                    conn.close()
                db.add_event(
                    event_id=f"evt_identity_auto_{uuid.uuid4().hex[:8]}",
                    event_type="identity_added",
                    source="julius-scanner",
                    data={"identity_id": identity_id, "target": target, "auto": True},
                )
        except Exception as e:
            logger.warning("Auto identity creation failed: %s", e)

        # ── AXIOM + Causal Functor pipeline ───────────────────────────────
        _run_axiom_pipeline(scan_id, target, open_ports, vulns)

    except Exception as e:
        logger.error("Scan %s failed: %s", scan_id, e)
        db.update_scan(scan_id, "failed", {"error": str(e)})


def _run_anonymized_scan_task(scan_id: str, target: str, ports: List[int], timeout: float, complexity: float):
    """Background anonymized scan task using VEIL transport."""
    try:
        open_ports = []
        for port in ports:
            result = _check_port_anonymized(target, port, timeout)
            if result["status"] == "open":
                open_ports.append(result)

        vulns = _detect_vulnerabilities(scan_id, target, open_ports)

        # Track revenue for anonymized scan
        _revenue_engine.process_transaction({
            'bytes': len(ports) * 100,
            'destination': target,
            'type': 'anonymized_scan'
        }, complexity=complexity)

        db.add_event(
            event_id=f"evt_veil_scan_{scan_id}",
            event_type="anonymized_scan_completed",
            source="julius-veil-scanner",
            data={
                "scan_id": scan_id,
                "target": target,
                "open_ports": len(open_ports),
                "vulns": len(vulns),
                "anonymized": True
            }
        )

        scan_results = {
            "target": target,
            "total_ports_scanned": len(ports),
            "open_ports": open_ports,
            "vulnerabilities": vulns,
            "vulnerability_count": len(vulns),
            "anonymized": True
        }
        db.update_scan(scan_id, "completed", scan_results)

        # Auto-create identity (preserved)
        try:
            existing = db.get_identities()
            handles = [i.get("handle") for i in existing]
            if target not in handles:
                identity_id = f"id-{uuid.uuid4().hex[:6]}"
                conn = db._connect()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO identities "
                        "(id, name, platform, handle, email, phone, created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (identity_id, f"Host_{target}", "anonymized_scan", target,
                         None, None, datetime.utcnow().isoformat()),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.warning("Auto identity creation failed: %s", e)

        # AXIOM pipeline
        _run_axiom_pipeline(scan_id, target, open_ports, vulns)

    except Exception as e:
        logger.error("Anonymized scan %s failed: %s", scan_id, e)
        db.update_scan(scan_id, "failed", {"error": str(e)})


# ── Endpoints (Original + VEIL additions) ─────────────────────────────────

@router.post("/scan")
async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
    """Start a network scan. AXIOM intelligence pipeline runs automatically on completion."""
    scan_id = f"scan_{uuid.uuid4().hex[:12]}"
    ports = req.ports
    if not ports:
        if req.scan_type == "quick":
            ports = TOP_PORTS[:15]
        elif req.scan_type == "full":
            ports = TOP_PORTS
        else:
            ports = TOP_PORTS[:10]

    db.create_scan(scan_id, req.target, req.scan_type)
    background_tasks.add_task(_run_scan_task, scan_id, req.target, ports, req.timeout)

    return {
        "scan_id": scan_id,
        "target": req.target,
        "scan_type": req.scan_type,
        "ports_to_scan": len(ports),
        "status": "running",
        "pipeline": "axiom+causal_functor will run on completion",
    }


@router.post("/anonymized-scan")
async def start_anonymized_scan(req: AnonymizedScanRequest, background_tasks: BackgroundTasks):
    """
    Start an anonymized network scan through VEIL (Tor + optional mixnet).
    
    Revenue tracking: Complexity multiplier scales fees per problem solved.
    - complexity=1.0: Standard anonymized scan
    - complexity=2.0: Deep dark web investigation
    - complexity=3.0: Intelligence gathering
    - complexity=5.0: Zero-day discovery
    """
    scan_id = f"veil_scan_{uuid.uuid4().hex[:12]}"
    ports = req.ports
    if not ports:
        if req.scan_type == "quick":
            ports = TOP_PORTS[:15]
        elif req.scan_type == "full":
            ports = TOP_PORTS
        else:
            ports = TOP_PORTS[:10]

    db.create_scan(scan_id, req.target, f"veil_{req.scan_type}")
    background_tasks.add_task(
        _run_anonymized_scan_task, 
        scan_id, req.target, ports, req.timeout, req.complexity
    )

    return {
        "scan_id": scan_id,
        "target": req.target,
        "scan_type": req.scan_type,
        "ports_to_scan": len(ports),
        "status": "running",
        "anonymized": True,
        "anonymity_level": req.anonymity_level,
        "revenue_tracking": True,
        "pipeline": "axiom+causal_functor will run on completion",
    }


@router.get("/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    """Get scan status, results, and AXIOM enrichment if available."""
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.get("/scans")
async def list_scans(limit: int = 20):
    scans = db.get_recent_scans(limit)
    return {"scans": scans, "total": len(scans)}


@router.post("/check-port")
async def check_single_port(req: PortCheckRequest):
    return _check_port(req.ip, req.port, req.timeout)


@router.get("/vulnerabilities")
async def list_vulnerabilities(
    scan_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
):
    return {"vulnerabilities": db.get_vulnerabilities(scan_id, severity, limit)}


@router.post("/scan/{scan_id}/analyse")
async def analyse_scan(scan_id: str):
    """
    Manually trigger AXIOM + Causal Functor analysis on an already-completed scan.
    Useful if the pipeline was skipped or you want to re-run analysis.
    """
    scan = db.get_scan(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    results = scan.get("results") or {}
    open_ports = results.get("open_ports", [])
    vulns = results.get("vulnerabilities", [])
    target = results.get("target") or scan.get("target", "")

    if not target:
        raise HTTPException(status_code=400, detail="Scan has no target")

    scan_payload = [{
        "target": target,
        "ports": [p["port"] for p in open_ports],
        "vulnerabilities": [v.get("cve_id") or v.get("title") for v in vulns],
        "services": {str(p["port"]): p["service"] for p in open_ports},
        "risk_score": _compute_risk_score(vulns),
        "open_ports_count": len(open_ports),
    }]

    from ..integration.pipeline import run_intelligence_pipeline
    pipeline_result = await run_intelligence_pipeline(
        scan_results=scan_payload,
        target=target,
        depth="deep",
    )
    return pipeline_result


@router.get("/revenue")
async def get_scanner_revenue():
    """Get total revenue from anonymized scanning operations."""
    return {
        "total_revenue_usd": _revenue_engine.get_total_revenue(),
        "currency": "USD",
        "source": "veil_anonymized_scanner"
    }

# """
# JULIUS Scanner Router — Network scanning, port scanning, vulnerability detection.
# Real TCP connectivity checks, banner grabbing, service detection.
# """

# import logging
# import socket
# import asyncio
# import uuid
# import time
# from datetime import datetime
# from typing import Optional, List, Dict, Any
# from fastapi import APIRouter, HTTPException, BackgroundTasks
# from pydantic import BaseModel

# from ..database import db

# logger = logging.getLogger(__name__)
# router = APIRouter(prefix="/api/scanner", tags=["Scanner"])

# # ── Well-known port/service mapping ───────────────────────────────────────
# WELL_KNOWN = {
#     21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
#     80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc",
#     139: "netbios-ssn", 143: "imap", 443: "https", 445: "microsoft-ds",
#     993: "imaps", 995: "pop3s", 1433: "mssql", 1521: "oracle",
#     3306: "mysql", 3389: "ms-wbt-server", 5432: "postgresql",
#     5900: "vnc", 6379: "redis", 8080: "http-proxy", 8443: "https-alt",
#     8888: "http-alt", 9090: "webmin", 27017: "mongodb",
# }

# TOP_PORTS = [
#     21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445,
#     993, 995, 1433, 1521, 3306, 3389, 5432, 5900, 5985, 6379,
#     8080, 8443, 8888, 9090, 27017,
# ]

# VULN_SIGNATURES = {
#     "ftp": [
#         {"pattern": "220", "severity": "info", "title": "FTP Service Detected", "description": "FTP server is running"},
#         {"pattern": "vsFTPd 2.3.4", "severity": "critical", "title": "vsFTPd 2.3.4 Backdoor (CVE-2011-2523)", "cve": "CVE-2011-2523"},
#     ],
#     "ssh": [
#         {"pattern": "SSH-", "severity": "info", "title": "SSH Service Detected"},
#         {"pattern": "OpenSSH_7.2", "severity": "high", "title": "OpenSSH 7.2 User Enumeration (CVE-2016-6210)", "cve": "CVE-2016-6210"},
#     ],
#     "http": [
#         {"pattern": "Apache/2.4.49", "severity": "critical", "title": "Apache 2.4.49 Path Traversal (CVE-2021-41773)", "cve": "CVE-2021-41773"},
#         {"pattern": "nginx", "severity": "info", "title": "Nginx Web Server Detected"},
#     ],
#     "smtp": [
#         {"pattern": "220", "severity": "info", "title": "SMTP Service Detected"},
#     ],
# }


# # ── Request Models ────────────────────────────────────────────────────────

# class ScanRequest(BaseModel):
#     target: str
#     scan_type: str = "quick"  # quick, full, stealth
#     ports: Optional[List[int]] = None
#     timeout: float = 2.0

# class PortCheckRequest(BaseModel):
#     ip: str
#     port: int
#     timeout: float = 2.0


# # ── Port scanning logic ──────────────────────────────────────────────────

# def _grab_banner(ip: str, port: int, timeout: float = 2.0) -> str:
#     """Try to grab a service banner from an open port."""
#     try:
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#             s.settimeout(timeout)
#             s.connect((ip, port))
#             # Send probe for HTTP
#             if port in (80, 8080, 8443, 443, 8000, 8888):
#                 s.send(b"HEAD / HTTP/1.0\r\nHost: target\r\n\r\n")
#             elif port == 25:
#                 pass  # SMTP sends banner on connect
#             else:
#                 s.send(b"\r\n")
#             banner = s.recv(1024).decode("utf-8", errors="ignore").strip()
#             return banner[:256]
#     except Exception:
#         return ""


# def _check_port(ip: str, port: int, timeout: float = 2.0) -> Dict[str, Any]:
#     """Check if a single TCP port is open."""
#     try:
#         with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#             s.settimeout(timeout)
#             result = s.connect_ex((ip, port))
#             if result == 0:
#                 service = WELL_KNOWN.get(port, "unknown")
#                 banner = _grab_banner(ip, port, timeout)
#                 return {
#                     "port": port,
#                     "status": "open",
#                     "service": service,
#                     "banner": banner,
#                 }
#             return {"port": port, "status": "closed", "service": "", "banner": ""}
#     except socket.timeout:
#         return {"port": port, "status": "filtered", "service": "", "banner": ""}
#     except Exception as e:
#         return {"port": port, "status": "error", "service": "", "banner": str(e)}


# def _detect_vulnerabilities(scan_id: str, host: str, open_ports: List[Dict]) -> List[Dict]:
#     """Check open ports for known vulnerability signatures."""
#     vulns = []
#     for port_info in open_ports:
#         if port_info["status"] != "open":
#             continue
#         service = port_info["service"]
#         banner = port_info.get("banner", "")

#         sigs = VULN_SIGNATURES.get(service, [])
#         for sig in sigs:
#             if sig["pattern"].lower() in banner.lower() or sig["severity"] == "info":
#                 vuln = {
#                     "host": host,
#                     "port": port_info["port"],
#                     "service": service,
#                     "severity": sig["severity"],
#                     "title": sig.get("title", "Unknown"),
#                     "description": sig.get("description", ""),
#                     "cve_id": sig.get("cve"),
#                     "banner": banner,
#                 }
#                 vulns.append(vuln)
#                 # Save to DB
#                 db.add_vulnerability(
#                     scan_id=scan_id,
#                     host=host,
#                     port=port_info["port"],
#                     service=service,
#                     severity=sig["severity"],
#                     title=sig.get("title", "Unknown"),
#                     description=sig.get("description", f"Banner: {banner}"),
#                     cve_id=sig.get("cve"),
#                 )
#     return vulns


# def _run_scan_task(scan_id: str, target: str, ports: List[int], timeout: float):
#     """Background scan task."""
#     try:
#         open_ports = []
#         all_results = []

#         for port in ports:
#             result = _check_port(target, port, timeout)
#             all_results.append(result)
#             if result["status"] == "open":
#                 open_ports.append(result)

#         # Detect vulnerabilities
#         vulns = _detect_vulnerabilities(scan_id, target, open_ports)

#         # Publish event
#         db.add_event(
#             event_id=f"evt_scan_{scan_id}",
#             event_type="scan_completed",
#             source="julius-scanner",
#             data={"scan_id": scan_id, "target": target, "open_ports": len(open_ports), "vulns": len(vulns)}
#         )

#         scan_results = {
#             "target": target,
#             "total_ports_scanned": len(ports),
#             "open_ports": open_ports,
#             "vulnerabilities": vulns,
#             "vulnerability_count": len(vulns),
#         }
#         db.update_scan(scan_id, "completed", scan_results)

#         # Auto-create identity profile for scanned target
#         try:
#             existing = db.get_identities()
#             handles = [i.get("handle") for i in existing]
#             if target not in handles:
#                 import uuid
#                 identity_id = f"id-{uuid.uuid4().hex[:6]}"
#                 conn = db._connect()
#                 try:
#                     conn.execute(
#                         "INSERT OR IGNORE INTO identities (id, name, platform, handle, email, phone, created_at) VALUES (?,?,?,?,?,?,?)",
#                         (identity_id, f"Host_{target}", "network_scan", target, None, None, datetime.utcnow().isoformat()),
#                     )
#                     conn.commit()
#                 finally:
#                     conn.close()
#                 db.add_event(
#                     event_id=f"evt_identity_auto_{uuid.uuid4().hex[:8]}",
#                     event_type="identity_added",
#                     source="julius-scanner",
#                     data={"identity_id": identity_id, "target": target, "auto": True},
#                 )
#         except Exception as e:
#             logger.warning(f"Auto identity creation failed: {e}")
#     except Exception as e:
#         logger.error(f"Scan {scan_id} failed: {e}")
#         db.update_scan(scan_id, "failed", {"error": str(e)})


# # ── Endpoints ─────────────────────────────────────────────────────────────

# @router.post("/scan")
# async def start_scan(req: ScanRequest, background_tasks: BackgroundTasks):
#     """Start a network scan against a target."""
#     scan_id = f"scan_{uuid.uuid4().hex[:12]}"

#     ports = req.ports
#     if not ports:
#         if req.scan_type == "quick":
#             ports = TOP_PORTS[:15]
#         elif req.scan_type == "full":
#             ports = TOP_PORTS
#         else:
#             ports = TOP_PORTS[:10]

#     db.create_scan(scan_id, req.target, req.scan_type)
#     background_tasks.add_task(_run_scan_task, scan_id, req.target, ports, req.timeout)

#     return {
#         "scan_id": scan_id,
#         "target": req.target,
#         "scan_type": req.scan_type,
#         "ports_to_scan": len(ports),
#         "status": "running",
#     }


# @router.get("/scan/{scan_id}")
# async def get_scan_status(scan_id: str):
#     """Get the status and results of a scan."""
#     scan = db.get_scan(scan_id)
#     if not scan:
#         raise HTTPException(status_code=404, detail="Scan not found")
#     return scan


# @router.get("/scans")
# async def list_scans(limit: int = 20):
#     """List recent scans."""
#     return {"scans": db.get_recent_scans(limit), "total": len(db.get_recent_scans(limit))}


# @router.post("/check-port")
# async def check_single_port(req: PortCheckRequest):
#     """Check a single TCP port."""
#     result = _check_port(req.ip, req.port, req.timeout)
#     return result


# @router.get("/vulnerabilities")
# async def list_vulnerabilities(scan_id: Optional[str] = None, severity: Optional[str] = None, limit: int = 100):
#     """List detected vulnerabilities."""
#     return {"vulnerabilities": db.get_vulnerabilities(scan_id, severity, limit)}
