"""
Build person-centric relationship edges from verified export profiles.

Relationships (evidence-backed only):
  - Person ↔ Package (maintainer / author)
  - Person ↔ Organization (employer / GOV.UK org / company field)
  - Person ↔ Contributor Profile (public registry or developer profile URL)
"""

from __future__ import annotations

from typing import Any

from .person_verification import ENTITY_ORGANIZATION, ENTITY_PERSON, ENTITY_SOFTWARE_ARTIFACT, classify_entity_type
from .stratum_omnis.entity_resolution_engine import canonical_key_from_public_url


def _canonical_key(profile: dict[str, Any]) -> str:
    identity = profile.get("identity_anchors") or {}
    return str(identity.get("canonical_entity_key") or profile.get("stratum_id") or "")


def _is_person(profile: dict[str, Any]) -> bool:
    verification = profile.get("verification") or {}
    if verification.get("is_real_person"):
        return True
    return classify_entity_type(profile) == ENTITY_PERSON


def _artifact_kind(profile: dict[str, Any]) -> str | None:
    et = (profile.get("verification") or {}).get("entity_type") or classify_entity_type(profile)
    if et == ENTITY_SOFTWARE_ARTIFACT:
        return "package"
    if et == ENTITY_ORGANIZATION:
        return "organization"
    return None


def _edge(
    *,
    source_key: str,
    target_key: str,
    relationship: str,
    source_stratum_id: str,
    target_stratum_id: str,
    evidence_url: str = "",
    evidence_type: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source_canonical_key": source_key,
        "target_canonical_key": target_key,
        "relationship": relationship,
        "source_stratum_id": source_stratum_id,
        "target_stratum_id": target_stratum_id,
        "evidence_url": evidence_url,
        "evidence_type": evidence_type,
        "metadata": metadata or {},
    }


def _contributor_profiles_for_person(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Public contributor / developer profile URLs discovered for this person."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    identity = profile.get("identity_anchors") or {}
    primary = str(identity.get("profile_url") or "")
    if primary.startswith("http") and primary not in seen:
        seen.add(primary)
        out.append(
            {
                "platform": identity.get("platform"),
                "handle": identity.get("handle"),
                "profile_url": primary,
                "relationship": "contributor_profile",
                "canonical_entity_key": _canonical_key(profile),
            }
        )
    for item in profile.get("public_identity_evidence") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        out.append(
            {
                "platform": item.get("platform"),
                "handle": item.get("handle"),
                "profile_url": url,
                "relationship": "contributor_profile",
                "evidence_type": item.get("type"),
                "source_field": item.get("source_field"),
                "parent_stratum_id": item.get("parent_stratum_id"),
            }
        )
    verification = profile.get("verification") or {}
    for url in verification.get("public_verification_links") or verification.get("public_profile_links") or []:
        u = str(url)
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append({"profile_url": u, "relationship": "contributor_profile"})
    return out[:25]


def build_relationship_graph(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    """Build export-level relationship graph and attach per-person relationship summaries."""
    by_key: dict[str, dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for profile in profiles:
        key = _canonical_key(profile)
        sid = str(profile.get("stratum_id") or "")
        if key:
            by_key[key] = profile
        if sid:
            by_id[sid] = profile

    edges: list[dict[str, Any]] = []
    nodes: dict[str, dict[str, Any]] = {}

    def _node(profile: dict[str, Any]) -> None:
        key = _canonical_key(profile)
        if not key or key in nodes:
            return
        verification = profile.get("verification") or {}
        nodes[key] = {
            "canonical_entity_key": key,
            "stratum_id": profile.get("stratum_id"),
            "entity_type": verification.get("entity_type") or classify_entity_type(profile),
            "display_name": (profile.get("identity_anchors") or {}).get("display_name")
            or (profile.get("identity_anchors") or {}).get("handle"),
            "export_tier": profile.get("export_tier"),
            "is_verified_person": bool(verification.get("is_real_person")),
        }

    # Index artifacts and organizations
    packages: list[dict[str, Any]] = []
    organizations: list[dict[str, Any]] = []
    for profile in profiles:
        _node(profile)
        kind = _artifact_kind(profile)
        key = _canonical_key(profile)
        sid = str(profile.get("stratum_id") or "")
        if kind == "package":
            packages.append({"canonical_entity_key": key, "stratum_id": sid, "name": (profile.get("identity_anchors") or {}).get("handle")})
        elif kind == "organization":
            organizations.append(
                {
                    "canonical_entity_key": key,
                    "stratum_id": sid,
                    "name": (profile.get("identity_anchors") or {}).get("display_name")
                    or (profile.get("identity_anchors") or {}).get("handle"),
                }
            )

    for profile in profiles:
        if not _is_person(profile):
            continue

        person_key = _canonical_key(profile)
        person_id = str(profile.get("stratum_id") or "")
        packages_linked: list[dict[str, Any]] = []
        orgs_linked: list[dict[str, Any]] = []
        contributor_profiles = _contributor_profiles_for_person(profile)

        # Derivation / merge provenance → package & org edges
        parent_id = str((profile.get("metadata") or {}).get("derived_from") or "")
        if parent_id and parent_id in by_id:
            parent = by_id[parent_id]
            parent_key = _canonical_key(parent)
            parent_kind = _artifact_kind(parent)
            if parent_kind == "package" and person_key and parent_key:
                evidence = ""
                for item in profile.get("public_identity_evidence") or []:
                    if isinstance(item, dict) and item.get("parent_stratum_id") == parent_id:
                        evidence = str(item.get("url") or "")
                        break
                edges.append(
                    _edge(
                        source_key=person_key,
                        target_key=parent_key,
                        relationship="maintains_package",
                        source_stratum_id=person_id,
                        target_stratum_id=parent_id,
                        evidence_url=evidence,
                        evidence_type="maintainer",
                    )
                )
                packages_linked.append(
                    {
                        "canonical_entity_key": parent_key,
                        "stratum_id": parent_id,
                        "package_name": (parent.get("identity_anchors") or {}).get("handle"),
                        "relationship": "maintains_package",
                        "evidence_url": evidence,
                    }
                )
            parent_raw = parent.get("raw_signals") or {}
            for contrib_page in parent_raw.get("contributor_page_candidates") or []:
                if not isinstance(contrib_page, dict):
                    continue
                page_url = str(contrib_page.get("profile_url") or "")
                if not page_url.startswith("http"):
                    continue
                contributor_profiles.append(
                    {
                        **contrib_page,
                        "relationship": "repository_contributors_page",
                        "linked_package_stratum_id": parent_id,
                    }
                )
                if person_key:
                    edges.append(
                        _edge(
                            source_key=person_key,
                            target_key=parent_key,
                            relationship="has_contributor_profile",
                            source_stratum_id=person_id,
                            target_stratum_id=parent_id,
                            evidence_url=page_url,
                            evidence_type="github_contributors_page",
                            metadata={"repository_url": contrib_page.get("repository_url")},
                        )
                    )

        for merged_id in profile.get("merged_stratum_ids") or []:
            mid = str(merged_id)
            if mid == person_id or mid not in by_id:
                continue
            other = by_id[mid]
            other_key = _canonical_key(other)
            other_kind = _artifact_kind(other)
            if other_kind == "package" and person_key and other_key:
                edges.append(
                    _edge(
                        source_key=person_key,
                        target_key=other_key,
                        relationship="maintains_package",
                        source_stratum_id=person_id,
                        target_stratum_id=mid,
                        evidence_type="merged_signal",
                    )
                )
                packages_linked.append(
                    {
                        "canonical_entity_key": other_key,
                        "stratum_id": mid,
                        "package_name": (other.get("identity_anchors") or {}).get("handle"),
                        "relationship": "maintains_package",
                    }
                )

        # Organization from situational / github company / govuk
        situational = profile.get("situational_intelligence") or {}
        org_name = str(situational.get("org") or "").strip()
        if org_name:
            org_key = f"organization:{org_name.lower().replace(' ', '-')}"
            for org_profile in organizations:
                if org_profile.get("name", "").lower() == org_name.lower():
                    org_key = org_profile["canonical_entity_key"]
                    oid = org_profile["stratum_id"]
                    edges.append(
                        _edge(
                            source_key=person_key,
                            target_key=org_key,
                            relationship="affiliated_with_organization",
                            source_stratum_id=person_id,
                            target_stratum_id=oid,
                            metadata={"org_name": org_name},
                        )
                    )
                    orgs_linked.append({**org_profile, "relationship": "affiliated_with_organization"})
                    break

        # Cross-link packages whose maintainer candidates match this person's public URLs
        person_urls = {
            str(u)
            for u in (
                (profile.get("identity_anchors") or {}).get("profile_url"),
                *[
                    str(item.get("url") or "")
                    for item in (profile.get("public_identity_evidence") or [])
                    if isinstance(item, dict)
                ],
            )
            if str(u).startswith("http")
        }
        for pkg_meta in packages:
            pkg_profile = by_key.get(pkg_meta["canonical_entity_key"]) or by_id.get(pkg_meta["stratum_id"])
            if not pkg_profile:
                continue
            pkg_key = pkg_meta["canonical_entity_key"]
            pkg_id = pkg_meta["stratum_id"]
            if any(p.get("stratum_id") == pkg_id for p in packages_linked):
                continue
            for cand in (pkg_profile.get("raw_signals") or {}).get("person_link_candidates") or []:
                if not isinstance(cand, dict):
                    continue
                cand_url = str(cand.get("profile_url") or "")
                if cand_url in person_urls and person_key and pkg_key:
                    edges.append(
                        _edge(
                            source_key=person_key,
                            target_key=pkg_key,
                            relationship="maintains_package",
                            source_stratum_id=person_id,
                            target_stratum_id=pkg_id,
                            evidence_url=cand_url,
                            evidence_type=str(cand.get("evidence_type") or "maintainer"),
                        )
                    )
                    packages_linked.append(
                        {
                            **pkg_meta,
                            "relationship": "maintains_package",
                            "evidence_url": cand_url,
                        }
                    )
                    break

        profile["relationship_graph"] = {
            "packages": packages_linked,
            "organizations": orgs_linked,
            "contributor_profiles": contributor_profiles,
        }

    # Contributor profile edges (person → public profile URL node)
    for profile in profiles:
        if not _is_person(profile):
            continue
        person_key = _canonical_key(profile)
        person_id = str(profile.get("stratum_id") or "")
        for contrib in profile.get("relationship_graph", {}).get("contributor_profiles") or []:
            url = str(contrib.get("profile_url") or "")
            target_key = canonical_key_from_public_url(url) or url
            if person_key and target_key:
                edges.append(
                    _edge(
                        source_key=person_key,
                        target_key=target_key,
                        relationship="has_contributor_profile",
                        source_stratum_id=person_id,
                        target_stratum_id=person_id,
                        evidence_url=url,
                        evidence_type=str(contrib.get("evidence_type") or "contributor_profile"),
                    )
                )

    person_nodes = [n for n in nodes.values() if n.get("is_verified_person") or n.get("entity_type") == ENTITY_PERSON]

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "person_nodes": len(person_nodes),
            "package_nodes": len(packages),
            "organization_nodes": len(organizations),
            "relationship_types": sorted({e["relationship"] for e in edges}),
        },
    }


def attach_relationship_graphs(profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Mutate profiles with relationship_graph and return export-level graph."""
    graph = build_relationship_graph(profiles)
    return profiles, graph
