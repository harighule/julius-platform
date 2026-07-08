"""Identity-resolution views over live STRATUM profiles."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .entity_resolution_engine import apply_canonical_resolution
from .profile_store import load_stratum_profiles


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _confidence(profile: dict[str, Any]) -> float:
    identity = profile.get("identity_anchors") or {}
    network = profile.get("network_signals") or {}
    situational = profile.get("situational_intelligence") or {}

    score = float(identity.get("resolution_confidence") or 0.5)
    if network.get("ip"):
        score += 0.08
    if network.get("hostnames"):
        score += 0.05
    if situational.get("org"):
        score += 0.04
    return round(min(0.99, score), 2)


def get_identity_resolution_snapshot(limit: int = 100) -> dict[str, Any]:
    profiles = load_stratum_profiles(limit)
    anchors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    ip_groups: dict[str, list[str]] = defaultdict(list)
    platform_groups: dict[str, int] = defaultdict(int)

    for profile in profiles:
        profile = apply_canonical_resolution(profile)
        identity = profile.get("identity_anchors") or {}
        resolution = profile.get("entity_resolution") or {}
        network = profile.get("network_signals") or {}
        handle = str(identity.get("handle") or "")
        platform = str(identity.get("platform") or "unknown")
        anchor_key = str(identity.get("canonical_entity_key") or f"{platform}:{handle}").lower()
        platform_groups[platform] += 1
        anchors[anchor_key].append(
            {
                "stratum_id": profile.get("stratum_id"),
                "handle": handle,
                "platform": platform,
                "canonical_name": identity.get("canonical_name"),
                "entity_type": identity.get("entity_type"),
                "match_strategy": resolution.get("match_strategy"),
                "confidence": _confidence(profile),
            }
        )
        ip = str(network.get("ip") or "")
        if ip:
            ip_groups[ip].append(str(profile.get("stratum_id") or ""))

    resolved = [
        {
            "anchor": anchor,
            "count": len(items),
            "profiles": items,
            "entity_type": items[0].get("entity_type") if items else "unknown",
            "canonical_name": items[0].get("canonical_name") if items else "",
            "resolution_confidence": round(sum(item["confidence"] for item in items) / len(items), 2),
        }
        for anchor, items in anchors.items()
    ]
    resolved.sort(key=lambda item: (item["count"], item["resolution_confidence"]), reverse=True)

    linked_ips = {ip: ids for ip, ids in ip_groups.items() if len(ids) >= 1}

    return {
        "generated_at": _utcnow(),
        "profiles_considered": len(profiles),
        "unique_identity_anchors": len(anchors),
        "platform_distribution": dict(platform_groups),
        "ip_anchor_groups": linked_ips,
        "resolved_identities": resolved[:25],
    }
