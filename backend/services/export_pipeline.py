"""
Shared STRATUM export pipeline for signals and OSINT routes.

Person-centric: derives verifiable people from artifact signals, merges canonically,
enriches, verifies, prioritizes verified people, and validates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .entity_resolution import get_engine as get_entity_engine
from .person_entity_extraction import derive_person_profiles
from .person_relationship_graph import attach_relationship_graphs
from .person_verification import (
    apply_person_verification,
    build_export_statistics,
    merge_canonical_entities,
    prioritize_export_profiles,
)
from .profile_enricher import enrich_profiles as enrich_batch
from .quality_validator import validate_batch
from .stratum_omnis.signal_enrichment import enrich_profiles as entity_centric_enrich


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_job_export(
    raw_profiles: list[dict[str, Any]],
    *,
    job_id: str | None = None,
    input_profile_count: int | None = None,
) -> dict[str, Any]:
    """
    Full export pipeline shared by /api/signals/export and /api/osint/collect/export.
    """
    raw_count = input_profile_count if input_profile_count is not None else len(raw_profiles)

    expanded, person_derivation_report = derive_person_profiles(raw_profiles)
    merged_profiles, merge_report = merge_canonical_entities(expanded)
    entity_enriched, entity_enrichment_report = entity_centric_enrich(merged_profiles)
    verified_profiles = [apply_person_verification(p) for p in entity_enriched]
    enriched_profiles = enrich_batch(verified_profiles)
    prioritized_profiles = prioritize_export_profiles(enriched_profiles)
    prioritized_profiles, relationship_graph = attach_relationship_graphs(prioritized_profiles)
    validation_report = validate_batch(prioritized_profiles)

    entity_engine = get_entity_engine()
    dup_groups, dup_matches = entity_engine.deduplicate_profiles(prioritized_profiles)
    statistics = build_export_statistics(
        prioritized_profiles,
        duplicate_count=len(dup_matches),
        input_profile_count=raw_count,
    )

    person_profiles = [
        p for p in prioritized_profiles if (p.get("verification") or {}).get("is_real_person")
    ]
    statistics["primary_export_object"] = "verified_person"
    statistics["person_profiles_count"] = len(person_profiles)

    payload: dict[str, Any] = {
        "export_timestamp": _utcnow(),
        "count": len(prioritized_profiles),
        "profiles": prioritized_profiles,
        "person_profiles": person_profiles,
        "relationship_graph": relationship_graph,
        "statistics": statistics,
        "quality_report": {
            "profiles_checked": validation_report.profiles_checked,
            "valid_profiles": validation_report.valid_profiles,
            "invalid_profiles": validation_report.invalid_profiles,
            "validation_rate": validation_report.validation_rate,
            "total_errors": validation_report.total_errors,
            "total_warnings": validation_report.total_warnings,
            "synthetic_detected": validation_report.synthetic_detected,
        },
        "dedup_report": {
            "duplicate_groups_found": len(dup_groups),
            "duplicates_count": len(dup_matches),
        },
        "merge_report": merge_report,
        "entity_enrichment_report": entity_enrichment_report,
        "person_derivation_report": person_derivation_report,
    }
    if job_id:
        payload["job_id"] = job_id
    return payload
