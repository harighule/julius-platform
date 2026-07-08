"""Safe stream-processing views over live STRATUM profiles and events."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from ...database import db
from .profile_store import load_stratum_profiles


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stream_event_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    metadata = profile.get("metadata") or {}
    identity = profile.get("identity_anchors") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    network = profile.get("network_signals") or {}

    source = str(metadata.get("source") or "unknown")
    if source == "public_github":
        event_type = "profile.github.public"
    elif source == "public_hostsearch":
        event_type = "profile.hostname.public"
    elif source == "public_osint":
        event_type = "profile.whois.public"
    else:
        event_type = "profile.public"

    return {
        "event_type": event_type,
        "source": source,
        "timestamp": metadata.get("collection_date"),
        "entity_id": profile.get("stratum_id"),
        "payload": {
            "handle": identity.get("handle"),
            "platform": identity.get("platform"),
            "followers": behavioral.get("followers", 0),
            "public_repos": behavioral.get("public_repos", 0),
            "ip": network.get("ip"),
            "hostnames": network.get("hostnames", []),
        },
    }


def get_stream_processing_snapshot(limit: int = 50) -> dict[str, Any]:
    profiles = load_stratum_profiles(limit)
    synthetic_stream = [_stream_event_from_profile(profile) for profile in profiles]
    live_events = db.get_recent_events(limit=100)

    source_counts = Counter(event["source"] for event in synthetic_stream)
    event_type_counts = Counter(event["event_type"] for event in synthetic_stream)
    bus_event_counts = Counter(event["event_type"] for event in live_events)

    return {
        "generated_at": _utcnow(),
        "synthetic_stream_count": len(synthetic_stream),
        "live_event_bus_count": len(live_events),
        "source_counts": dict(source_counts),
        "synthetic_event_types": dict(event_type_counts),
        "event_bus_types": dict(bus_event_counts),
        "recent_stream_events": synthetic_stream[:10],
    }
