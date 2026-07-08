"""Entity-centric enrichment over real public STRATUM signals.

This module does not create profiles or synthesize source data. It only merges
metadata already present in collected public-source profiles and annotates each
profile with entity-level enrichment context.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .entity_resolution_engine import apply_canonical_resolution, registered_domain, source_url


SOURCE_CATEGORY_MAP = {
    "public_github": "public_social_presence",
    "public_gitlab": "public_social_presence",
    "public_npm": "public_technology",
    "public_pypi": "public_technology",
    "public_govuk": "public_government_dataset",
    "public_spending_context": "public_transparency_dataset",
    "public_gdelt": "public_publication_activity",
    "public_openstreetmap": "public_institutional_geospatial",
    "public_hostsearch": "public_website_metadata",
    "public_ip_geocontext": "public_website_metadata",
    "public_osint": "public_registry_signal",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _source(profile: dict[str, Any]) -> str:
    return str((profile.get("metadata") or {}).get("source") or "unknown")


def _category(profile: dict[str, Any]) -> str:
    return SOURCE_CATEGORY_MAP.get(_source(profile), "public_metadata")


def _platform(profile: dict[str, Any]) -> str:
    return str((profile.get("identity_anchors") or {}).get("platform") or "unknown")


def _org(profile: dict[str, Any]) -> str:
    return str((profile.get("situational_intelligence") or {}).get("org") or "").strip()


def _domains(profile: dict[str, Any]) -> list[str]:
    network = profile.get("network_signals") or {}
    domains: list[str] = []
    for host in _as_list(network.get("hostnames")):
        domain = registered_domain(host)
        if domain:
            domains.append(domain)
    url = source_url(profile)
    if url:
        domain = registered_domain(url)
        if domain:
            domains.append(domain)
    return list(dict.fromkeys(domains))


def _entity_key(profile: dict[str, Any]) -> str:
    profile = apply_canonical_resolution(profile)
    return str((profile.get("identity_anchors") or {}).get("canonical_entity_key") or profile.get("stratum_id"))


def _enrichment_level(source_count: int, category_count: int) -> str:
    if source_count >= 4 and category_count >= 3:
        return "STRONG"
    if source_count >= 2 and category_count >= 2:
        return "MODERATE"
    return "BASIC"


def _confidence(source_count: int, category_count: int, domain_count: int, org_count: int) -> float:
    score = 0.42
    score += min(0.22, source_count * 0.055)
    score += min(0.22, category_count * 0.075)
    score += min(0.08, domain_count * 0.025)
    score += min(0.06, org_count * 0.03)
    return round(min(0.99, score), 2)


def _aggregate_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    sources = sorted({_source(profile) for profile in items})
    categories = sorted({_category(profile) for profile in items})
    domains = sorted({domain for profile in items for domain in _domains(profile)})
    orgs = sorted({org for profile in items if (org := _org(profile))})
    platforms = sorted({_platform(profile) for profile in items})
    source_counts = Counter(_source(profile) for profile in items)
    key = _entity_key(items[0]) if items else ""

    return {
        "canonical_entity_key": key,
        "source_count": len(sources),
        "signal_count": len(items),
        "source_categories": categories,
        "source_distribution": dict(source_counts),
        "enrichment_level": _enrichment_level(len(sources), len(categories)),
        "confidence_score": _confidence(len(sources), len(categories), len(domains), len(orgs)),
        "related_domains": domains[:25],
        "related_organizations": orgs[:25],
        "related_platforms": platforms[:25],
    }


def _update_behavioral_intelligence(profile: dict[str, Any], group: list[dict[str, Any]], aggregate: dict[str, Any]) -> None:
    behavioral = profile.setdefault("behavioral_intelligence", {})
    platforms = list(
        dict.fromkeys(
            [
                *[str(item) for item in _as_list(behavioral.get("platform_presence")) if item],
                *aggregate["related_platforms"],
            ]
        )
    )
    tech_stack = list(
        dict.fromkeys(
            str(item)
            for member in group
            for item in _as_list((member.get("behavioral_intelligence") or {}).get("tech_stack"))
            if item
        )
    )

    public_repos = max(int((member.get("behavioral_intelligence") or {}).get("public_repos") or 0) for member in group)
    followers = max(int((member.get("behavioral_intelligence") or {}).get("followers") or 0) for member in group)
    contribution = max(int((member.get("behavioral_intelligence") or {}).get("contribution_score") or 0) for member in group)
    observed_activity = max(
        int((member.get("behavioral_intelligence") or {}).get("digital_activity_score") or 0)
        for member in group
    )
    diversity_bonus = min(25, len(aggregate["source_categories"]) * 6 + len(aggregate["related_platforms"]) * 3)

    behavioral["platform_presence"] = platforms
    behavioral["tech_stack"] = tech_stack[:30]
    behavioral["public_repos"] = max(int(behavioral.get("public_repos") or 0), public_repos)
    behavioral["followers"] = max(int(behavioral.get("followers") or 0), followers)
    behavioral["contribution_score"] = max(int(behavioral.get("contribution_score") or 0), contribution)
    behavioral["digital_activity_score"] = min(
        100,
        max(int(behavioral.get("digital_activity_score") or 0), observed_activity + diversity_bonus),
    )


def _update_derived_signals(profile: dict[str, Any], aggregate: dict[str, Any]) -> None:
    derived = profile.setdefault("derived_signals", {})
    category_count = len(aggregate["source_categories"])
    source_count = aggregate["source_count"]
    domain_count = len(aggregate["related_domains"])
    platform_count = len(aggregate["related_platforms"])
    actual_diversity = min(100, category_count * 18 + source_count * 8 + domain_count * 3 + platform_count * 4)
    derived["source_diversity_score"] = max(int(derived.get("source_diversity_score") or 0), actual_diversity)
    patterns = list(dict.fromkeys([*_as_list(derived.get("patterns")), *aggregate["source_categories"]]))
    derived["patterns"] = patterns
    derived["provenance"] = _as_list(derived.get("provenance"))


def _profile_enrichment_provenance(profile: dict[str, Any], group: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_id = str(profile.get("stratum_id") or "")
    provenance: list[dict[str, Any]] = []
    for member in group:
        metadata = member.get("metadata") or {}
        identity = member.get("identity_anchors") or {}
        provenance.append(
            {
                "operation": "entity_centric_enrichment",
                "source_stratum_id": member.get("stratum_id"),
                "source": metadata.get("source"),
                "category": _category(member),
                "platform": identity.get("platform"),
                "contributed_to": current_id,
                "raw_signal_keys": list((member.get("raw_signals") or {}).keys()),
                "collected_at": metadata.get("collection_date"),
            }
        )
    return provenance


def enrich_profiles(profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    working = [apply_canonical_resolution(deepcopy(profile)) for profile in profiles]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for profile in working:
        groups[_entity_key(profile)].append(profile)

    aggregates = {key: _aggregate_group(items) for key, items in groups.items()}
    enriched: list[dict[str, Any]] = []
    for profile in working:
        key = _entity_key(profile)
        group = groups[key]
        aggregate = aggregates[key]
        _update_behavioral_intelligence(profile, group, aggregate)
        _update_derived_signals(profile, aggregate)
        profile["entity_enrichment"] = {
            **aggregate,
            "provenance": _profile_enrichment_provenance(profile, group),
            "enriched_at": _utcnow(),
            "enrichment_version": "entity_enrichment_v1",
        }
        enriched.append(profile)

    level_counts = Counter((profile.get("entity_enrichment") or {}).get("enrichment_level", "BASIC") for profile in enriched)
    category_counts = Counter(
        category
        for profile in enriched
        for category in (profile.get("entity_enrichment") or {}).get("source_categories", [])
    )
    report = {
        "generated_at": _utcnow(),
        "profiles_enriched": len(enriched),
        "canonical_entities": len(groups),
        "multi_signal_entities": sum(1 for items in groups.values() if len(items) > 1),
        "multi_source_entities": sum(1 for aggregate in aggregates.values() if aggregate["source_count"] > 1),
        "enrichment_levels": dict(level_counts),
        "source_categories": dict(category_counts),
    }
    return enriched, report
