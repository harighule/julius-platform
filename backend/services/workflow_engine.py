"""
JULIUS Workflow Engine — Orchestrates multi-step automated investigations.
Chains scanner, exploit, identity, behavioral, darkweb, files, and live subsystems.
"""
import logging
import json
import re
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

WORKFLOW_TEMPLATES = {
    "recon": {
        "name": "Target Reconnaissance",
        "description": "Full reconnaissance on a target IP: scan, IP lookup, CVE check, dark web search",
        "steps": [
            {"service": "scan", "action": "port_scan", "params": {"target": "{{input.target}}"}},
            {"service": "live", "action": "ip_lookup", "params": {"ip": "{{input.target}}"}},
            {"service": "live", "action": "cve_check", "params": {}},
            {"service": "darkweb", "action": "search", "params": {"query": "{{input.target}}"}},
        ],
    },
    "track": {
        "name": "Attacker Tracking",
        "description": "Correlate an identity across all data sources",
        "steps": [
            {"service": "identity", "action": "resolve", "params": {"query": "{{input.name}}"}},
            {"service": "identity", "action": "graph", "params": {}},
            {"service": "events", "action": "search", "params": {"query": "{{input.name}}"}},
        ],
    },
    "incident": {
        "name": "Incident Response",
        "description": "Automated investigation of a security incident",
        "steps": [
            {"service": "scan", "action": "port_scan"},
            {"service": "exploit", "action": "analyze"},
            {"service": "stratum", "action": "analyze"},
            {"service": "csie", "action": "infer"},
            {"service": "causal_functor", "action": "reason"},
            {"service": "kronos", "action": "scale"},
            {"service": "axiom", "action": "compress"},
        ],
    },
    "kronos_pipeline": {
        "name": "Integrated Security Intelligence Pipeline",
        "description": "Scanner -> Exploit -> STRATUM -> CSIE -> CAUSAL FUNCTOR -> KRONOS -> AXIOM",
        "steps": [
            {"service": "scan", "action": "port_scan", "params": {}},
            {"service": "exploit", "action": "run", "params": {}},
            {"service": "stratum", "action": "analyze", "params": {}},
            {"service": "csie", "action": "infer", "params": {}},
            {"service": "causal_functor", "action": "reason", "params": {}},
            {"service": "kronos", "action": "scale", "params": {}},
            {"service": "axiom", "action": "compress", "params": {}},
            {"service": "self_evolution", "action": "analyze", "params": {}},
        ],
    },
    "autonomous_pipeline": {
        "name": "Autonomous Evolution Pipeline",
        "description": "KRONOS -> AXIOM -> Self Evolution",
        "steps": [
            {"service": "kronos", "action": "analyze", "params": {}},
            {"service": "axiom", "action": "compress", "params": {}},
            {"service": "self_evolution", "action": "analyze", "params": {}},
            {"service": "self_evolution", "action": "patch", "params": {}},
            {"service": "self_evolution", "action": "review", "params": {}}
        ],
    },
}


def _db():
    from ..database import db
    return db


async def execute_workflow(workflow_id: int):
    """Execute all steps of a workflow sequentially."""
    db = _db()
    workflow = db.get_workflow_with_steps(workflow_id)
    if not workflow:
        logger.error(f"Workflow {workflow_id} not found")
        return
    db.update_workflow_status(workflow_id, "running")
    context: Dict[str, Any] = {}
    steps = workflow.get("steps", [])
    if not steps:
        actions = workflow.get("actions", [])
        if isinstance(actions, list):
            for i, step_def in enumerate(actions):
                if isinstance(step_def, dict):
                    db.add_workflow_step(
                        workflow_id, i,
                        step_def.get("service", "unknown"),
                        step_def.get("action", "unknown"),
                        step_def.get("params", {}),
                    )
            steps = db.get_workflow_steps(workflow_id)
    for step in steps:
        step_idx = step["step_index"]
        db.update_workflow_step(workflow_id, step_idx, "running")
        try:
            params = _resolve_params(step.get("params", {}), context)
            result = await _execute_step(step["service"], step["action"], params, context)
            context[f"step_{step_idx}_result"] = result
            db.update_workflow_step(workflow_id, step_idx, "completed", result)
        except Exception as e:
            logger.error(f"Workflow {workflow_id} step {step_idx} failed: {e}")
            db.update_workflow_step(workflow_id, step_idx, "failed", {"error": str(e)})
            db.update_workflow_status(workflow_id, "failed")
            return
    db.update_workflow_status(workflow_id, "completed")
    db.add_event(
        event_id=f"evt_wf_done_{uuid.uuid4().hex[:8]}",
        event_type="workflow_completed",
        source="julius-workflow-engine",
        data={"workflow_id": workflow_id, "name": workflow["name"], "steps": len(steps)},
    )
    logger.info(f"Workflow {workflow_id} completed: {len(steps)} steps")
    return context


async def _execute_step(service: str, action: str, params: dict, context: dict) -> dict:
    """Execute a single workflow step by dispatching to the appropriate service."""
    db = _db()
    if service == "scan" and action == "port_scan":
        from ..routers.scanner import _check_port, _detect_vulnerabilities, TOP_PORTS
        target = params.get("target", "127.0.0.1")
        scan_id = f"scan_wf_{uuid.uuid4().hex[:8]}"
        db.create_scan(scan_id, target, "workflow")
        open_ports = []
        for port in TOP_PORTS:
            r = _check_port(target, port, 1.5)
            if r["status"] == "open":
                open_ports.append(r)
        vulns = _detect_vulnerabilities(scan_id, target, open_ports)
        db.update_scan(scan_id, "completed", {"open_ports": open_ports, "vulnerabilities": vulns})
        return {"scan_id": scan_id, "open_ports": len(open_ports), "vulnerabilities": len(vulns), "ports": open_ports}
    elif service == "live" and action == "ip_lookup":
        import httpx
        ip = params.get("ip", "127.0.0.1")
        results = {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip}")
                if resp.status_code == 200:
                    results["geolocation"] = resp.json()
        except Exception as e:
            results["error"] = str(e)
        return {"ip": ip, "intel": results}
    elif service == "live" and action == "cve_check":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get("https://services.nvd.nist.gov/rest/json/cves/2.0", params={"resultsPerPage": 10})
                data = resp.json()
            cves = []
            for item in data.get("vulnerabilities", [])[:10]:
                cve = item.get("cve", {})
                cves.append({"id": cve.get("id"), "published": cve.get("published")})
            return {"cves": cves, "total": data.get("totalResults", 0)}
        except Exception as e:
            return {"error": str(e)}
    elif service == "darkweb" and action == "search":
        query = params.get("query", "")
        try:
            from ..routers.darkweb import _robin_available, _check_tor
            if _robin_available:
                tor = _check_tor()
                if tor["status"] == "up":
                    from search import get_search_results
                    results = get_search_results(query, max_workers=3)
                    return {"results": len(results), "query": query, "sample": results[:5]}
            return {"results": 0, "query": query, "note": "Robin/Tor not available"}
        except Exception as e:
            return {"error": str(e), "query": query}
    elif service == "identity" and action == "resolve":
        query = params.get("query", "")
        identities = db.get_identities()
        matches = [i for i in identities if query.lower() in (i.get("name", "").lower() + " " + (i.get("email") or "") + " " + (i.get("handle") or ""))]
        return {"query": query, "matches": len(matches), "identities": matches[:10]}
    elif service == "identity" and action == "graph":
        from ..routers.identity import _build_graph
        graph = _build_graph()
        return {"nodes": len(graph.get("nodes", [])), "edges": len(graph.get("edges", []))}
    elif service == "behavioral" and action == "check_patterns":
        patterns = db.get_behavioral_patterns()
        alerts = db.get_behavioral_alerts(20)
        return {"patterns": len(patterns), "recent_alerts": len(alerts)}
    elif service == "events" and action in ("recent", "search"):
        events = db.get_recent_events(50)
        query = params.get("query", "")
        if query:
            events = [e for e in events if query.lower() in json.dumps(e).lower()]
        return {"events": len(events), "sample": events[:10]}
    elif service == "stratum" and action == "analyze":
        from .stratum_omnis import get_stratum_runtime
        return {
            "status": "success",
            "runtime": get_stratum_runtime(),
        }
    elif service == "csie" and action == "infer":
        from .stratum_omnis import get_csie_snapshot
        return {
            "status": "success",
            "csie": get_csie_snapshot(),
        }
    elif service == "causal_functor" and action == "reason":
        from .causal_functor import get_causal_functor_diagnostics
        return {
            "status": "success",
            "diagnostics": get_causal_functor_diagnostics(),
        }
    elif service == "kronos" and action == "scale":
        from .kronos_service import KronosService
        service_obj = KronosService()
        return {
            "status": "success",
            "kronos_status": service_obj.get_status(),
            "kronos_analysis": service_obj.analyze(),
        }
    elif service == "kronos" and action == "analyze":
        from .kronos_service import KronosService
        engine = KronosService()
        return {
            "status": "success",
            "analysis": engine.analyze(),
        }
    elif service == "axiom" and action == "compress":
        from .axiom.axiom_compressor import compression_report
        return {
            "status": "success",
            "compression_results": compression_report(),
        }
    elif service == "self_evolution" and action == "analyze":
        from .self_evolution import SelfEvolution
        engine = SelfEvolution()
        return {
            "status": "success",
            "analysis": engine.analyze_repository(),
        }
    elif service == "self_evolution" and action == "patch":
        from .self_evolution import SelfEvolution
        engine = SelfEvolution()
        return {
            "status": "success",
            "patch": engine.generate_patch(),
        }
    elif service == "self_evolution" and action == "review":
        from .self_evolution import SelfEvolution
        engine = SelfEvolution()
        return {
            "status": "success",
            "review": engine.review_queue(),
        }
    elif service == "exploit" and action == "analyze":
        scan_data = context.get("step_0_result", {})
        ports = scan_data.get("ports", [])
        findings = []

        service_map = {
            "mysql": {
                "module": "mysql_default_creds",
                "risk": "high"
            },
            "microsoft-ds": {
                "module": "smb_null_session",
                "risk": "medium"
            },
            "http": {
                "module": "http_dir_traversal",
                "risk": "high"
            },
            "https": {
                "module": "ssl_vulns",
                "risk": "medium"
            },
            "dns": {
                "module": "dns_zone_transfer",
                "risk": "high"
            }
        }

        for port_info in ports:
            service_name = port_info.get("service")
            if service_name in service_map:
                findings.append({
                    "port": port_info.get("port"),
                    "service": service_name,
                    "recommended_module": service_map[service_name]["module"],
                    "risk": service_map[service_name]["risk"]
                })

        return {
            "status": "success",
            "ports_analyzed": len(ports),
            "recommendations": findings
        }
    else:
        return {"error": f"Unknown service/action: {service}/{action}"}


def _resolve_params(params: dict, context: dict) -> dict:
    """Replace template variables like {{step_0_result.scan_id}} with actual values."""
    resolved = {}
    for key, val in params.items():
        if isinstance(val, str) and "{{" in val:
            for match in re.findall(r'\{\{(.+?)\}\}', val):
                parts = match.split(".")
                value = context
                for p in parts:
                    if isinstance(value, dict):
                        value = value.get(p, "")
                    else:
                        value = ""
                        break
                val = val.replace(f"{{{{{match}}}}}", str(value))
        resolved[key] = val
    return resolved


def create_from_template(template_name: str, input_params: dict) -> Optional[int]:
    """Create a workflow from a named template with input parameters."""
    template = WORKFLOW_TEMPLATES.get(template_name)
    if not template:
        return None
    db = _db()
    result = db.add_workflow(
        name=f"{template['name']} - {datetime.utcnow().strftime('%H:%M')}",
        description=template["description"],
        trigger_type="template",
        actions=template["steps"],
    )
    workflow_id = result["id"]
    for i, step_def in enumerate(template["steps"]):
        params = step_def.get("params", {})
        resolved = {}
        for k, v in params.items():
            if isinstance(v, str) and "{{input." in v:
                key = v.replace("{{input.", "").replace("}}", "")
                resolved[k] = input_params.get(key, v)
            else:
                resolved[k] = v
        db.add_workflow_step(workflow_id, i, step_def["service"], step_def["action"], resolved)
    return workflow_id