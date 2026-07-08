"""
STRATUM Person Verification + Canonical Entity Merge

Transforms collected public signals into verifiable entity profiles.
Uses only evidence already present in profiles — no synthetic identities.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from .stratum_omnis.entity_resolution_engine import apply_canonical_resolution, source_url

# Export-facing entity types (manager requirement)
ENTITY_PERSON = "person"
ENTITY_ORGANIZATION = "organization"
ENTITY_PUBLISHER = "publisher"
ENTITY_SOFTWARE_ARTIFACT = "software_artifact"
ENTITY_PUBLIC_RECORD = "public_record"
ENTITY_DOMAIN = "domain"
ENTITY_UNKNOWN = "unknown"

PERSON_PLATFORMS = frozenset({"github", "gitlab"})
SOFTWARE_PLATFORMS = frozenset({"npm", "pypi"})
PERSON_SOURCE_PREFIXES = ("public_github", "public_gitlab", "derived_public_person")
DERIVED_PERSON_SOURCE = "derived_public_person"
DERIVED_ORG_SOURCE = "derived_public_organization"
PUBLISHER_SOURCES = frozenset({"public_gdelt"})
RECORD_SOURCES = frozenset({"public_govuk", "public_spending_context", "public_hostsearch", "public_osint"})

# Priority when choosing canonical representative (higher = preferred)
_ENTITY_PRIORITY = {
    ENTITY_PERSON: 100,
    ENTITY_ORGANIZATION: 70,
    ENTITY_PUBLISHER: 30,
    ENTITY_PUBLIC_RECORD: 25,
    ENTITY_SOFTWARE_ARTIFACT: 20,
    ENTITY_DOMAIN: 15,
    ENTITY_UNKNOWN: 5,
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_key(profile: dict[str, Any]) -> str:
    p = apply_canonical_resolution(deepcopy(profile))
    return str((p.get("identity_anchors") or {}).get("canonical_entity_key") or p.get("stratum_id") or "")


def _profile_url(profile: dict[str, Any]) -> str:
    identity = profile.get("identity_anchors") or {}
    url = str(identity.get("profile_url") or "").strip()
    if url:
        return url
    return source_url(profile)


def _extract_links(profile: dict[str, Any]) -> list[str]:
    links: list[str] = []
    identity = profile.get("identity_anchors") or {}
    for candidate in (identity.get("profile_url"), _profile_url(profile)):
        u = str(candidate or "").strip()
        if u.startswith("http"):
            links.append(u)
    for item in _as_list(profile.get("public_identity_evidence")):
        if isinstance(item, dict):
            u = str(item.get("url") or "").strip()
            if u.startswith("http"):
                links.append(u)
    raw = profile.get("raw_signals") or {}
    for block in raw.values():
        if not isinstance(block, dict):
            continue
        for key in ("url", "link", "profile_url", "html_url", "web_url"):
            u = str(block.get(key) or "").strip()
            if u.startswith("http"):
                links.append(u)
    return list(dict.fromkeys(links))


def _collect_identity_evidence(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured public identity evidence (URLs must already exist in signals)."""
    evidence: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in _as_list(profile.get("public_identity_evidence")):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            evidence.append(dict(item))

    metadata = profile.get("metadata") or {}
    identity = profile.get("identity_anchors") or {}
    platform = str(identity.get("platform") or "")
    source = str(metadata.get("source") or "")
    parent_id = str(metadata.get("derived_from") or "")

    profile_url = str(identity.get("profile_url") or "").strip()
    if profile_url and profile_url not in seen_urls:
        seen_urls.add(profile_url)
        evidence.append(
            {
                "type": "primary_profile",
                "platform": platform,
                "url": profile_url,
                "handle": str(identity.get("handle") or ""),
                "source_field": "identity_anchors.profile_url",
                "parent_stratum_id": parent_id or None,
                "parent_source": metadata.get("parent_artifact_source"),
            }
        )

    for link in _extract_links(profile):
        if link in seen_urls:
            continue
        seen_urls.add(link)
        evidence.append(
            {
                "type": "linked_public_source",
                "platform": platform or source,
                "url": link,
                "handle": str(identity.get("handle") or ""),
                "source_field": "raw_signals",
                "parent_stratum_id": parent_id or None,
                "parent_source": metadata.get("parent_artifact_source"),
            }
        )

    return evidence[:30]


def classify_entity_type(profile: dict[str, Any]) -> str:
    """Map collected profile to export entity type."""
    profile = apply_canonical_resolution(profile)
    identity = profile.get("identity_anchors") or {}
    metadata = profile.get("metadata") or {}
    platform = str(identity.get("platform") or "").lower()
    source = str(metadata.get("source") or "").lower()
    key = str(identity.get("canonical_entity_key") or "")

    if source == DERIVED_PERSON_SOURCE or source in PERSON_SOURCE_PREFIXES:
        return ENTITY_PERSON
    profile_url = str(identity.get("profile_url") or "")
    if "/government/people/" in profile_url and platform == "govuk":
        return ENTITY_PERSON
    if source == DERIVED_ORG_SOURCE or (key.startswith("organization:") and platform == "govuk"):
        return ENTITY_ORGANIZATION
    if key.startswith("package:") or (platform in SOFTWARE_PLATFORMS and source in {"public_npm", "public_pypi"}):
        return ENTITY_SOFTWARE_ARTIFACT
    if key.startswith("developer:") or platform in PERSON_PLATFORMS:
        return ENTITY_PERSON
    if platform in {"npm", "pypi"} and source == DERIVED_PERSON_SOURCE:
        return ENTITY_PERSON
    if key.startswith("publisher:") or source in PUBLISHER_SOURCES:
        return ENTITY_PUBLISHER
    if key.startswith("domain:") or platform in {"domain", "hostname"}:
        return ENTITY_DOMAIN
    if key.startswith("organization:") or source in {"public_spending_context"}:
        return ENTITY_ORGANIZATION
    if key.startswith("public-record:") or source in RECORD_SOURCES:
        return ENTITY_PUBLIC_RECORD
    if key.startswith("place:") or platform == "openstreetmap":
        return ENTITY_PUBLIC_RECORD

    omnis_type = str(identity.get("entity_type") or "")
    if omnis_type == "digital_identity":
        return ENTITY_PERSON
    if omnis_type in {ENTITY_ORGANIZATION, ENTITY_PUBLISHER, ENTITY_PUBLIC_RECORD, ENTITY_SOFTWARE_ARTIFACT}:
        return omnis_type
    if omnis_type == "domain":
        return ENTITY_DOMAIN
    if omnis_type == "place":
        return ENTITY_PUBLIC_RECORD

    handle = str(identity.get("handle") or "")
    if handle and platform in PERSON_PLATFORMS:
        return ENTITY_PERSON
    return ENTITY_UNKNOWN


def _collect_evidence(profile: dict[str, Any]) -> tuple[list[str], list[str], int, list[dict[str, Any]]]:
    """Return (public_profile_links, public_identity_sources, evidence_count, structured_evidence)."""
    metadata = profile.get("metadata") or {}
    identity = profile.get("identity_anchors") or {}
    platform = str(identity.get("platform") or "")
    source = str(metadata.get("source") or "")

    structured = _collect_identity_evidence(profile)
    links = [str(item.get("url") or "") for item in structured if item.get("url")]
    links = list(dict.fromkeys([*links, *_extract_links(profile)]))

    sources: list[str] = []
    if source:
        sources.append(source)
    if platform and platform not in sources:
        sources.append(platform)
    for item in structured:
        plat = str(item.get("platform") or "")
        if plat and plat not in sources:
            sources.append(plat)

    evidence = 0
    if links:
        evidence += 1
    if structured:
        evidence += 1
    if str(identity.get("handle") or "").strip():
        evidence += 1
    if int((profile.get("behavioral_intelligence") or {}).get("followers") or 0) > 0:
        evidence += 1
    if int((profile.get("behavioral_intelligence") or {}).get("public_repos") or 0) > 0:
        evidence += 1
    if len(_as_list((profile.get("behavioral_intelligence") or {}).get("platform_presence"))) > 1:
        evidence += 1
    if (profile.get("entity_enrichment") or {}).get("source_count", 0) > 1:
        evidence += 1

    return links, list(dict.fromkeys(sources)), max(evidence, len(links), len(structured)), structured


def verify_profile(profile: dict[str, Any], *, group_size: int = 1) -> dict[str, Any]:
    """
    Build verification block from public evidence only.
    """
    profile = apply_canonical_resolution(deepcopy(profile))
    entity_type = classify_entity_type(profile)
    links, id_sources, evidence_count, structured_evidence = _collect_evidence(profile)

    identity = profile.get("identity_anchors") or {}
    platform = str(identity.get("platform") or "").lower()
    handle = str(identity.get("handle") or "").strip()
    key = str(identity.get("canonical_entity_key") or "")
    metadata = profile.get("metadata") or {}

    has_person_anchor = (
        entity_type == ENTITY_PERSON
        or platform in PERSON_PLATFORMS
        or key.startswith("developer:")
        or metadata.get("source") == DERIVED_PERSON_SOURCE
    )
    has_verifiable_handle = bool(handle) and platform in PERSON_PLATFORMS
    has_public_link = bool(links)
    has_structured_evidence = len(structured_evidence) > 0

    # Person: require platform handle or developer key + public URL from real sources
    is_real_person = False
    if has_person_anchor and (has_verifiable_handle or key.startswith("developer:")):
        if metadata.get("source") == DERIVED_PERSON_SOURCE and has_public_link and has_structured_evidence:
            is_real_person = True
        elif evidence_count >= 2 or (has_public_link and has_verifiable_handle):
            is_real_person = True
        elif group_size > 1 and evidence_count >= 1 and has_public_link:
            is_real_person = True

    # Non-person entities
    is_real_entity = is_real_person
    if entity_type == ENTITY_ORGANIZATION and (handle or links):
        is_real_entity = True
    elif entity_type == ENTITY_PUBLISHER and links:
        is_real_entity = True
    elif entity_type in {ENTITY_PUBLIC_RECORD, ENTITY_DOMAIN} and links:
        is_real_entity = True
    elif entity_type == ENTITY_SOFTWARE_ARTIFACT and links:
        is_real_entity = True

    confidence = 0.35
    if is_real_person:
        confidence = 0.55 + min(0.35, evidence_count * 0.08) + (0.1 if group_size > 1 else 0)
        if has_public_link:
            confidence += 0.08
        if int((profile.get("behavioral_intelligence") or {}).get("followers") or 0) > 10:
            confidence += 0.05
    elif is_real_entity:
        confidence = 0.5 + min(0.25, evidence_count * 0.06)
    else:
        confidence = 0.25 + min(0.15, evidence_count * 0.04)

    enrichment = profile.get("entity_enrichment") or {}
    if enrichment.get("enrichment_level") == "STRONG":
        confidence = min(0.99, confidence + 0.12)
    elif enrichment.get("enrichment_level") == "MODERATE":
        confidence = min(0.99, confidence + 0.06)

    verification = {
        "is_real_entity": bool(is_real_entity),
        "is_real_person": bool(is_real_person),
        "entity_type": entity_type,
        "verification_confidence": round(min(0.99, confidence), 2),
        "evidence_count": evidence_count,
        "public_profile_links": links[:25],
        "public_verification_links": links[:25],
        "public_identity_sources": id_sources[:15],
        "public_identity_evidence": structured_evidence[:30],
        "verification_method": "public_evidence_only",
        "verified_at": _utcnow(),
    }
    profile["verification"] = verification
    profile["public_identity_evidence"] = structured_evidence[:30]
    identity["entity_type"] = entity_type
    return profile


def _merge_raw_signals(group: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for member in group:
        raw = member.get("raw_signals") or {}
        for k, v in raw.items():
            if k not in merged:
                merged[k] = v
    return merged


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple signal rows into one canonical entity profile."""
    if len(group) == 1:
        return verify_profile(group[0], group_size=1)

    # Pick best representative
    scored = []
    for p in group:
        p = apply_canonical_resolution(deepcopy(p))
        et = classify_entity_type(p)
        scored.append((_ENTITY_PRIORITY.get(et, 0), len(_extract_links(p)), p))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    primary = deepcopy(scored[0][2])

    # Merge intelligence from all members
    behavioral = primary.setdefault("behavioral_intelligence", {})
    platforms: list[str] = []
    tech: list[str] = []
    max_followers = 0
    max_repos = 0
    max_contrib = 0
    max_activity = 0
    orgs: list[str] = []

    for member in group:
        b = member.get("behavioral_intelligence") or {}
        platforms.extend(str(x) for x in _as_list(b.get("platform_presence")) if x)
        tech.extend(str(x) for x in _as_list(b.get("tech_stack")) if x)
        max_followers = max(max_followers, int(b.get("followers") or 0))
        max_repos = max(max_repos, int(b.get("public_repos") or 0))
        max_contrib = max(max_contrib, int(b.get("contribution_score") or 0))
        max_activity = max(max_activity, int(b.get("digital_activity_score") or 0))
        org = str((member.get("situational_intelligence") or {}).get("org") or "").strip()
        if org:
            orgs.append(org)

    behavioral["platform_presence"] = list(dict.fromkeys(platforms))[:30]
    behavioral["tech_stack"] = list(dict.fromkeys(tech))[:30]
    behavioral["followers"] = max_followers
    behavioral["public_repos"] = max_repos
    behavioral["contribution_score"] = max_contrib
    behavioral["digital_activity_score"] = max(max_activity, int(behavioral.get("digital_activity_score") or 0))

    situational = primary.setdefault("situational_intelligence", {})
    if orgs:
        situational["org"] = orgs[0]

    primary["raw_signals"] = _merge_raw_signals(group)
    primary["merged_signal_count"] = len(group)
    primary["merged_stratum_ids"] = [str(m.get("stratum_id")) for m in group if m.get("stratum_id")]

    all_links: list[str] = []
    all_sources: list[str] = []
    merged_evidence: list[dict[str, Any]] = []
    for member in group:
        links, sources, _, structured = _collect_evidence(member)
        all_links.extend(links)
        all_sources.extend(sources)
        merged_evidence.extend(structured)
    if merged_evidence:
        seen_ev: set[str] = set()
        deduped_evidence: list[dict[str, Any]] = []
        for item in merged_evidence:
            url = str(item.get("url") or "")
            if url and url not in seen_ev:
                seen_ev.add(url)
                deduped_evidence.append(item)
        primary["public_identity_evidence"] = deduped_evidence[:30]
    identity = primary.setdefault("identity_anchors", {})
    if all_links and not identity.get("profile_url"):
        identity["profile_url"] = all_links[0]

    primary["entity_merge"] = {
        "canonical_entity_key": _canonical_key(primary),
        "merged_profiles": len(group),
        "merged_at": _utcnow(),
        "contributing_sources": list(dict.fromkeys(all_sources)),
    }

    return verify_profile(primary, group_size=len(group))


def merge_canonical_entities(profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    One export profile per canonical entity key (not one per document/URL).
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for profile in profiles:
        key = _canonical_key(profile)
        if key:
            groups[key].append(profile)

    merged = [_merge_group(items) for items in groups.values()]
    type_counts = Counter(classify_entity_type(p) for p in merged)
    person_verified = sum(1 for p in merged if (p.get("verification") or {}).get("is_real_person"))

    report = {
        "input_profiles": len(profiles),
        "canonical_entities": len(merged),
        "compression_ratio": round(len(profiles) / max(1, len(merged)), 2),
        "entity_type_distribution": dict(type_counts),
        "verified_people": person_verified,
        "multi_signal_entities": sum(1 for p in merged if int(p.get("merged_signal_count") or 1) > 1),
    }
    return merged, report


def apply_person_verification(profile: dict[str, Any]) -> dict[str, Any]:
    """Convenience: classify + verify single profile."""
    return verify_profile(profile, group_size=int(profile.get("merged_signal_count") or 1))


_EXPORT_TIER_ORDER = {
    "verified_person": 0,
    "unverified_person": 1,
    "organization": 2,
    "artifact": 3,
    "document": 4,
    "other": 5,
}


def assign_export_tier(profile: dict[str, Any]) -> str:
    verification = profile.get("verification") or {}
    entity_type = verification.get("entity_type") or classify_entity_type(profile)
    if verification.get("is_real_person"):
        return "verified_person"
    if entity_type == ENTITY_PERSON:
        return "unverified_person"
    if entity_type == ENTITY_ORGANIZATION:
        return "organization"
    if entity_type in {ENTITY_SOFTWARE_ARTIFACT, ENTITY_DOMAIN}:
        return "artifact"
    if entity_type in {ENTITY_PUBLISHER, ENTITY_PUBLIC_RECORD}:
        return "document"
    return "other"


def prioritize_export_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort export output: verified people first, then other types, then by confidence."""
    working: list[dict[str, Any]] = []
    for profile in profiles:
        copy = deepcopy(profile)
        copy["export_tier"] = assign_export_tier(copy)
        working.append(copy)

    def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        tier = item.get("export_tier") or "other"
        verification = item.get("verification") or {}
        return (
            _EXPORT_TIER_ORDER.get(str(tier), 99),
            0 if verification.get("is_real_person") else 1,
            -float(verification.get("verification_confidence") or 0),
            -float((item.get("derived_signals") or {}).get("signal_strength_score") or 0),
            str(item.get("stratum_id") or ""),
        )

    working.sort(key=_sort_key)
    return working


def build_export_statistics(
    profiles: list[dict[str, Any]],
    *,
    duplicate_count: int = 0,
    input_profile_count: int | None = None,
) -> dict[str, Any]:
    """Export statistics aligned with manager requirements."""
    total = len(profiles)
    if total == 0:
        return {
            "total_profiles": 0,
            "verified_people": 0,
            "verified_organizations": 0,
            "verified_publishers": 0,
            "verified_software_artifacts": 0,
            "verified_public_records": 0,
            "verification_rate": 0.0,
            "person_profile_ratio": 0.0,
            "publisher_only_profiles": 0,
            "document_only_profiles": 0,
            "source_distribution": {},
            "duplicate_rate": 0.0,
            "average_signal_strength": 0.0,
            "average_verification_confidence": 0.0,
            "export_tier_counts": {},
            "raw_collected_profiles": input_profile_count or 0,
            "canonical_entities": 0,
        }

    verified_people = 0
    verified_orgs = 0
    verified_publishers = 0
    verified_software = 0
    verified_records = 0
    publisher_only = 0
    document_only = 0
    source_distribution: dict[str, int] = {}
    verified_any = 0
    signal_strength_sum = 0.0
    person_confidence_sum = 0.0
    tier_counts: dict[str, int] = {}

    for profile in profiles:
        v = profile.get("verification") or {}
        et = v.get("entity_type") or ENTITY_UNKNOWN
        if v.get("is_real_person"):
            verified_people += 1
            person_confidence_sum += float(v.get("verification_confidence") or 0)
        tier = str(profile.get("export_tier") or assign_export_tier(profile))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if v.get("is_real_entity"):
            verified_any += 1
        if et == ENTITY_ORGANIZATION and v.get("is_real_entity"):
            verified_orgs += 1
        if et == ENTITY_PUBLISHER and v.get("is_real_entity"):
            verified_publishers += 1
        if et == ENTITY_SOFTWARE_ARTIFACT and v.get("is_real_entity"):
            verified_software += 1
        if et == ENTITY_PUBLIC_RECORD and v.get("is_real_entity"):
            verified_records += 1
        if et == ENTITY_PUBLISHER and not v.get("is_real_person"):
            publisher_only += 1
        if et == ENTITY_PUBLIC_RECORD and not v.get("is_real_person"):
            document_only += 1

        for src in (profile.get("entity_merge") or {}).get("contributing_sources") or []:
            source_distribution[src] = source_distribution.get(src, 0) + 1
        meta_src = (profile.get("metadata") or {}).get("source", "unknown")
        source_distribution[str(meta_src)] = source_distribution.get(str(meta_src), 0) + 1

        signal_strength_sum += float((profile.get("derived_signals") or {}).get("signal_strength_score") or 0)

    return {
        "total_profiles": total,
        "verified_people": verified_people,
        "verified_organizations": verified_orgs,
        "verified_publishers": verified_publishers,
        "verified_software_artifacts": verified_software,
        "verified_public_records": verified_records,
        "verification_rate": round(verified_any / total * 100, 1),
        "person_profile_ratio": round(verified_people / total * 100, 1),
        "publisher_only_profiles": publisher_only,
        "document_only_profiles": document_only,
        "source_distribution": source_distribution,
        "duplicate_rate": round(duplicate_count / total * 100, 1) if total else 0.0,
        "average_signal_strength": round(signal_strength_sum / total, 1),
        "average_verification_confidence": round(person_confidence_sum / verified_people, 2) if verified_people else 0.0,
        "export_tier_counts": tier_counts,
        "raw_collected_profiles": input_profile_count or total,
        "canonical_entities": total,
    }
