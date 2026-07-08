"""Feature-store style views over live STRATUM profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .entity_resolution_engine import apply_canonical_resolution
from .profile_store import load_stratum_profiles


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def engineer_features(profile: dict[str, Any]) -> dict[str, Any]:
    profile = apply_canonical_resolution(profile)
    identity = profile.get("identity_anchors") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    situational = profile.get("situational_intelligence") or {}
    network = profile.get("network_signals") or {}
    risk = profile.get("risk_profile") or {}
    metadata = profile.get("metadata") or {}
    derived = profile.get("derived_signals") or {}

    public_repos = int(behavioral.get("public_repos") or 0)
    followers = int(behavioral.get("followers") or 0)
    activity = int(behavioral.get("digital_activity_score") or 0)
    contribution = int(behavioral.get("contribution_score") or 0)
    platform_presence = behavioral.get("platform_presence") or []
    tech_stack = behavioral.get("tech_stack") or []

    risk_numeric = {"LOW": 20, "MEDIUM": 50, "HIGH": 80}.get(str(risk.get("overall_risk") or "LOW").upper(), 20)
    geo_density = sum(1 for value in [situational.get("city"), situational.get("region"), situational.get("timezone")] if value)

    return {
        "stratum_id": profile.get("stratum_id"),
        "handle": identity.get("handle"),
        "platform": identity.get("platform"),
        "canonical_entity_key": identity.get("canonical_entity_key"),
        "canonical_entity_hash": identity.get("canonical_entity_hash"),
        "entity_type": identity.get("entity_type"),
        "source": metadata.get("source"),
        "collection_job_id": metadata.get("collection_job_id"),
        "feature_vector": {
            "activity_score": activity,
            "contribution_score": contribution,
            "followers": followers,
            "public_repos": public_repos,
            "platform_presence_count": len(platform_presence),
            "tech_stack_count": len(tech_stack),
            "has_ip_signal": bool(network.get("ip")),
            "hostname_count": len(network.get("hostnames") or []),
            "risk_numeric": risk_numeric,
            "geo_density": geo_density,
            "public_social_activity_score": int(derived.get("public_social_activity_score") or 0),
            "public_digital_pattern_score": int(derived.get("public_digital_pattern_score") or 0),
            "public_spending_context_score": int(derived.get("public_spending_context_score") or 0),
            "source_diversity_score": int(derived.get("source_diversity_score") or 0),
        },
        "dimensions": {
            "organization": situational.get("org"),
            "country": situational.get("country"),
            "city": situational.get("city"),
            "timezone": situational.get("timezone"),
            "tech_stack": tech_stack,
            "derived_patterns": derived.get("patterns") or [],
            "provenance": derived.get("provenance") or [],
        },
    }


def get_feature_store_snapshot(limit: int = 25) -> dict[str, Any]:
    profiles = load_stratum_profiles(limit)
    feature_rows = [engineer_features(profile) for profile in profiles]
    avg_activity = round(
        sum(row["feature_vector"]["activity_score"] for row in feature_rows) / len(feature_rows),
        2,
    ) if feature_rows else 0.0
    avg_risk = round(
        sum(row["feature_vector"]["risk_numeric"] for row in feature_rows) / len(feature_rows),
        2,
    ) if feature_rows else 0.0
    avg_digital_pattern = round(
        sum(row["feature_vector"]["public_digital_pattern_score"] for row in feature_rows) / len(feature_rows),
        2,
    ) if feature_rows else 0.0
    avg_spending_context = round(
        sum(row["feature_vector"]["public_spending_context_score"] for row in feature_rows) / len(feature_rows),
        2,
    ) if feature_rows else 0.0

    return {
        "generated_at": _utcnow(),
        "count": len(feature_rows),
        "summary": {
            "avg_activity_score": avg_activity,
            "avg_risk_numeric": avg_risk,
            "avg_public_digital_pattern_score": avg_digital_pattern,
            "avg_public_spending_context_score": avg_spending_context,
        },
        "features": feature_rows,
    }
