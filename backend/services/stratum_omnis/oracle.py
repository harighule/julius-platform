"""Safe ORACLE-style predictions over public STRATUM profiles."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .profile_store import load_stratum_profiles


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def predict_profile(profile: dict[str, Any]) -> dict[str, Any]:
    identity = profile.get("identity_anchors") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    metadata = profile.get("metadata") or {}
    handle = str(identity.get("handle") or "unknown")
    platform = str(identity.get("platform") or "unknown")
    repos = int(behavioral.get("public_repos") or 0)
    followers = int(behavioral.get("followers") or 0)
    activity = int(behavioral.get("digital_activity_score") or 0)

    if platform in {"github", "gitlab"}:
        action = "monitor_repository_growth" if repos >= 3 else "watch_public_profile_changes"
        domain = "commercial"
        confidence = round(min(0.92, 0.45 + repos * 0.04 + followers * 0.01), 2)
        rationale = "Public developer-profile activity indicates ongoing technical footprint growth."
    elif platform in {"npm", "pypi"}:
        action = "monitor_package_release_and_maintainer_changes"
        domain = "commercial"
        confidence = round(min(0.86, 0.46 + activity / 220), 2)
        rationale = "Public package metadata gives a low-risk signal for software ecosystem activity."
    elif platform == "govuk":
        action = "monitor_official_public_record_updates"
        domain = "geopolitical"
        confidence = 0.64
        rationale = "Official GOV.UK public records are suitable for periodic public-context refresh."
    elif platform == "hostname":
        action = "watch_domain_and_org_changes"
        domain = "environmental"
        confidence = 0.58
        rationale = "Public hostname and org metadata suggest infrastructure ownership worth periodic re-checks."
    else:
        action = "refresh_public_osint_profile"
        domain = "personal"
        confidence = round(min(0.8, 0.35 + activity / 200), 2)
        rationale = "Profile has low-risk public visibility with enough activity to justify refresh."

    return {
        "stratum_id": profile.get("stratum_id"),
        "handle": handle,
        "platform": platform,
        "source": metadata.get("source"),
        "predictions": {
            "24h": {
                "domain": domain,
                "action": action,
                "confidence": confidence,
                "rationale": rationale,
            },
            "7d": {
                "domain": domain,
                "action": action,
                "confidence": round(max(0.3, confidence - 0.04), 2),
                "rationale": rationale,
            },
            "30d": {
                "domain": domain,
                "action": action,
                "confidence": round(max(0.25, confidence - 0.1), 2),
                "rationale": rationale,
            },
        },
    }


def get_oracle_snapshot(limit: int = 10) -> dict[str, Any]:
    profiles = load_stratum_profiles(limit)
    return {
        "generated_at": _utcnow(),
        "count": len(profiles),
        "predictions": [predict_profile(profile) for profile in profiles],
    }
