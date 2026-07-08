"""
backend/integration/pipeline.py

Complete intelligence pipeline per manager's architecture:
  STRATUM → CSIE → CAUSAL FUNCTOR → KRONOS → AXIOM

scanner / osint output
  → CSIE categorical semantic analysis
  → AXIOM algebraic analysis
  → Causal Functor reasoning
  → Enriched result
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("julius.pipeline")


async def run_intelligence_pipeline(
    scan_results: List[Dict[str, Any]],
    osint_data: Optional[Dict[str, Any]] = None,
    target: Optional[str] = None,
    depth: str = "standard",
) -> Dict[str, Any]:
    """
    Full pipeline: scan data → CSIE → AXIOM → causal functor → enriched report.
    """
    result: Dict[str, Any] = {
        "target": target,
        "depth": depth,
        "csie_analysis": {},
        "axiom_findings": [],
        "causal_graph": {},
        "causal_inferences": [],
        "summary": {},
    }

    # ── Stage 0: CSIE categorical semantic analysis ────────────────────────
    try:
        from ..services.csie_chat_bridge import csie_pipeline_analyse
        csie_result = await csie_pipeline_analyse(
            scan_results=scan_results,
            osint_data=osint_data or {},
            target=target or "unknown",
        )
        result["csie_analysis"] = csie_result
        logger.info("CSIE stage complete for %s", target)
    except Exception as exc:
        logger.warning("CSIE stage failed (non-fatal): %s", exc)
        result["csie_error"] = str(exc)

    # ── Stage 1: AXIOM algebraic analysis ─────────────────────────────────
    try:
        from ..routers.axiom import analyse_pipeline_data, PipelineAnalysisRequest
        axiom_req    = PipelineAnalysisRequest(
            scan_results=scan_results,
            osint_data=osint_data,
            target=target,
            analysis_depth=depth,
        )
        axiom_result = await analyse_pipeline_data(axiom_req)
        result["axiom_findings"] = axiom_result.get("scan_findings", [])
        result["axiom_osint"]    = axiom_result.get("osint_summary")
        result["axiom_meta"]     = {
            "total_analysed": axiom_result.get("total_scans_analysed", 0),
            "critical_count": axiom_result.get("critical_count", 0),
            "high_count":     axiom_result.get("high_count", 0),
        }
        logger.info(
            "AXIOM stage complete: %d findings, %d critical",
            len(result["axiom_findings"]),
            result["axiom_meta"]["critical_count"],
        )
    except Exception as exc:
        logger.warning("AXIOM stage failed (non-fatal): %s", exc)
        result["axiom_error"] = str(exc)

    # ── Stage 2: Causal Functor graph + inference ──────────────────────────
    try:
        from ..services.causal_functor import (
            get_causal_functor_graph,
            get_causal_functor_inference,
        )
        causal_graph = get_causal_functor_graph(limit=10)
        result["causal_graph"] = causal_graph

        critical = [
            f for f in result["axiom_findings"]
            if f.get("severity") in ("critical", "high")
        ]
        if critical:
            src_id = critical[0].get("target") or target
            inferences = get_causal_functor_inference(
                source_id=src_id,
                direction="forward",
                limit=5,
                max_depth=3,
            )
            result["causal_inferences"] = inferences
        logger.info("Causal Functor stage complete")
    except Exception as exc:
        logger.warning("Causal Functor stage failed (non-fatal): %s", exc)
        result["causal_error"] = str(exc)

    # ── Stage 3: APEX extended causal analysis (if deep mode) ─────────────
    if depth == "deep":
        try:
            from ..routers.apex import (
                _detect_confounding_cohomology,
                _causal_path_integral,
            )
            obs = [
                {
                    "ports": len(sr.get("ports", [])),
                    "vulns": len(sr.get("vulnerabilities", [])),
                    "risk":  sr.get("risk_score", 0),
                }
                for sr in scan_results
            ]
            result["apex_level6"] = _detect_confounding_cohomology(obs, "risk")
            result["apex_level10"] = _causal_path_integral(obs, "risk", n_paths=50)
            logger.info("APEX deep analysis complete")
        except Exception as exc:
            logger.warning("APEX stage failed (non-fatal): %s", exc)
            result["apex_error"] = str(exc)

    # ── Stage 4: Summary ───────────────────────────────────────────────────
    result["summary"] = _build_summary(result)
    return result


def _build_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    findings   = result.get("axiom_findings", [])
    severities = [f.get("severity", "low") for f in findings]
    csie       = result.get("csie_analysis", {})

    return {
        "total_targets_analysed": len(findings),
        "severity_breakdown": {
            "critical": severities.count("critical"),
            "high":     severities.count("high"),
            "medium":   severities.count("medium"),
            "low":      severities.count("low"),
        },
        "causal_paths_found":    len(result.get("causal_inferences", [])),
        "osint_indicators":      (result.get("axiom_osint") or {}).get("total_indicators", 0),
        "csie_morphisms":        len(csie.get("morphism_chain", [])),
        "csie_global_section":   csie.get("global_section_exists", False),
        "pipeline_stages_completed": sum([
            1 if result.get("csie_analysis")   else 0,
            1 if result.get("axiom_findings") is not None else 0,
            1 if result.get("causal_graph")   is not None else 0,
            1 if result.get("apex_level6")    else 0,
        ]),
        "recommendation": _recommend(severities),
        "pipeline_chain": "CSIE → AXIOM → Causal Functor" + (" → APEX" if result.get("apex_level6") else ""),
    }


def _recommend(severities: List[str]) -> str:
    if "critical" in severities:
        return "IMMEDIATE ACTION REQUIRED — critical threats detected"
    if "high" in severities:
        return "Escalate to Tier-2 analyst — high-severity indicators present"
    if "medium" in severities:
        return "Monitor and schedule follow-up scan within 24 hours"
    return "No immediate action required — continue routine monitoring"