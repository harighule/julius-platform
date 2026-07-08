"""Safe CSIE-style semantic classification over public STRATUM profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .csie_bootstrap import ProfileConversionResult, build_csie_from_profiles
from .csie_cech import CechSolver, CechSolveResult
from .profile_store import load_stratum_profiles

CSIE_ENGINE_MODE = "mvp_cech"
CSIE_ENGINE_VERSION = "day4"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_csie_engine_status() -> dict[str, Any]:
    return {
        "mode": CSIE_ENGINE_MODE,
        "version": CSIE_ENGINE_VERSION,
        "available": True,
    }


def classify_profile(profile: dict[str, Any]) -> dict[str, Any]:
    identity = profile.get("identity_anchors") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    metadata = profile.get("metadata") or {}
    network = profile.get("network_signals") or {}

    platform = str(identity.get("platform") or "unknown")
    source = str(metadata.get("source") or "unknown")
    objects = [platform, source]
    morphisms: list[str] = []

    if platform in {"github", "gitlab"}:
        objects.append("developer_identity")
        morphisms.append("public_code_activity")
    if platform in {"npm", "pypi"}:
        objects.append("package_registry_artifact")
        morphisms.append("software_distribution_signal")
    if platform == "govuk":
        objects.append("official_public_record")
        morphisms.append("public_governance_context")
    if network.get("ip"):
        objects.append("network_anchor")
        morphisms.append("public_geocontext")
    if behavioral.get("tech_stack"):
        objects.append("technology_context")
        morphisms.append("stack_affinity")

    return {
        "stratum_id": profile.get("stratum_id"),
        "semantic_objects": objects,
        "morphisms": morphisms,
        "context": {
            "platform": platform,
            "source": source,
            "country": (profile.get("situational_intelligence") or {}).get("country"),
        },
    }


def _classify_profile_with_csie(
    profile: dict[str, Any],
    conversion: ProfileConversionResult,
    solver: CechSolver,
) -> dict[str, Any]:
    classification = classify_profile(profile)
    concept_ids = tuple(sorted({concept_id for _, concept_id in conversion.section_ids}))
    covering = solver.sheaf.get_covering(conversion.context_ids)
    result = solver.validate_global_consistency(covering, concept_ids)
    classification.update(_runtime_fields(covering, result))
    return classification


def _runtime_fields(covering: list[str], result: CechSolveResult) -> dict[str, Any]:
    return {
        "csie_engine": {
            "mode": CSIE_ENGINE_MODE,
            "version": CSIE_ENGINE_VERSION,
        },
        "covering": list(covering),
        "global_section_summary": {
            "count": len(result.global_sections),
            "concept_ids": [section.concept_id for section in result.global_sections],
        },
        "h1_residual": float(result.h1_residual),
        "uncertainty_level": result.uncertainty,
        "diagnostics": {
            "global_section_count": result.diagnostics.global_section_count,
            "conflict_count": result.diagnostics.conflict_count,
            "knowledge_gap_count": result.diagnostics.knowledge_gap_count,
            "polysemy_count": result.diagnostics.polysemy_count,
            "uncertainty": result.diagnostics.uncertainty,
        },
    }


def get_csie_snapshot(limit: int = 10) -> dict[str, Any]:
    profiles = load_stratum_profiles(limit)
    bootstrap = build_csie_from_profiles(profiles)
    solver = CechSolver(bootstrap.sheaf)
    return {
        "generated_at": _utcnow(),
        "csie_engine": get_csie_engine_status(),
        "count": len(profiles),
        "classifications": [
            _classify_profile_with_csie(profile, conversion, solver)
            for profile, conversion in zip(profiles, bootstrap.conversions)
        ],
    }
