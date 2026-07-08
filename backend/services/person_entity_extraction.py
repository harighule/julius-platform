"""
Derive verifiable person and organization profiles from public artifact signals.

Uses only URLs and handles present in collected API payloads — never invents
usernames, profile URLs, or identities from display names.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .stratum_omnis.entity_resolution_engine import canonical_key_from_public_url


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stratum_id() -> str:
    return f"STRID-DER-{uuid.uuid4().hex[:8].upper()}"


_GITHUB_RESERVED = frozenset(
    {
        "settings",
        "orgs",
        "organizations",
        "topics",
        "marketplace",
        "features",
        "enterprise",
        "pricing",
        "login",
        "signup",
        "explore",
        "collections",
        "events",
        "sponsors",
        "about",
        "site",
        "apps",
        "pulls",
        "issues",
        "notifications",
    }
)

_HANDLE_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]{0,37}[a-zA-Z0-9])?$")


@dataclass(frozen=True)
class PublicProfileRef:
    platform: str
    handle: str
    profile_url: str
    evidence_type: str
    source_field: str
    display_name: str = ""


def _valid_handle(handle: str) -> bool:
    text = str(handle or "").strip()
    if not text or len(text) > 39:
        return False
    if " " in text or "@" in text:
        return False
    return bool(_HANDLE_RE.match(text))


def _normalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        text = f"https:{text}"
    if not text.startswith("http"):
        text = f"https://{text}"
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def parse_public_profile_url(url: str) -> PublicProfileRef | None:
    """Parse allowlisted public profile URLs; return None if not a known profile page."""
    normalized = _normalize_url(url)
    if not normalized:
        return None

    parsed = urlparse(normalized)
    host = parsed.netloc.lower()
    parts = [segment for segment in parsed.path.split("/") if segment]

    if host in {"github.com", "www.github.com"}:
        if not parts or parts[0] in _GITHUB_RESERVED:
            return None
        login = parts[0]
        if not _valid_handle(login):
            return None
        if len(parts) >= 2 and parts[1] == "contributors":
            return None
        profile_url = f"https://github.com/{login}"
        evidence = "github_contributor_page" if len(parts) >= 3 and parts[2] == "graphs" and len(parts) >= 4 and parts[3] == "contributors" else "github_profile"
        if len(parts) >= 2 and parts[1] not in {"graphs", "blob", "tree", "commits", "pull", "issues", "discussions", "packages", "projects"}:
            evidence = "github_profile"
        return PublicProfileRef("github", login, profile_url, evidence, "url")

    if host in {"gitlab.com", "www.gitlab.com"}:
        if not parts or parts[0] in {"explore", "public", "users", "dashboard", "groups"}:
            return None
        username = parts[0]
        if not _valid_handle(username):
            return None
        return PublicProfileRef("gitlab", username, f"https://gitlab.com/{username}", "gitlab_profile", "url")

    if host in {"www.npmjs.com", "npmjs.com"}:
        if len(parts) >= 2 and parts[0] == "~":
            username = parts[1]
            if _valid_handle(username):
                return PublicProfileRef("npm", username, f"https://www.npmjs.com/~{username}", "npm_maintainer_page", "url")

    if host in {"pypi.org", "www.pypi.org"}:
        if len(parts) >= 2 and parts[0] == "user":
            username = parts[1]
            if _valid_handle(username):
                return PublicProfileRef("pypi", username, f"https://pypi.org/user/{username}/", "pypi_author_page", "url")

    if host in {"www.gov.uk", "gov.uk"}:
        if len(parts) >= 3 and parts[0] == "government" and parts[1] == "organisations":
            slug = parts[2]
            if slug:
                org_url = f"https://www.gov.uk/government/organisations/{slug}"
                return PublicProfileRef("govuk", slug, org_url, "govuk_organisation_page", "url")
        if len(parts) >= 3 and parts[0] == "government" and parts[1] == "people":
            slug = parts[2]
            if slug and slug not in {"all", "search"}:
                staff_url = f"https://www.gov.uk/government/people/{slug}"
                display = slug.replace("-", " ").title()
                return PublicProfileRef("govuk", slug, staff_url, "govuk_staff_page", "url", display)

    return None


def collect_staff_link_candidates_from_govuk(result: dict[str, Any]) -> list[dict[str, Any]]:
    """GOV.UK public staff / people pages linked from search results."""
    candidates: list[dict[str, Any]] = []
    for key in ("link", "href"):
        ref = parse_public_profile_url(str(result.get(key) or ""))
        if ref and ref.evidence_type == "govuk_staff_page":
            candidates.append(_ref_to_candidate(ref, f"govuk_result.{key}"))
    for person in result.get("people") or []:
        if not isinstance(person, dict):
            continue
        link = str(person.get("link") or "")
        title = str(person.get("title") or "")
        if link.startswith("/government/people/"):
            url = f"https://www.gov.uk{link}"
            ref = parse_public_profile_url(url)
            if ref:
                item = _ref_to_candidate(ref, "people.link")
                if title:
                    item["display_name"] = title
                candidates.append(item)
    details = result.get("details") or {}
    if isinstance(details, dict):
        for body in details.get("body") or []:
            if not isinstance(body, dict):
                continue
            for key in ("href", "link"):
                ref = parse_public_profile_url(str(body.get(key) or ""))
                if ref and ref.evidence_type == "govuk_staff_page":
                    candidates.append(_ref_to_candidate(ref, f"details.body.{key}"))
    return _dedupe_candidates(candidates)


def collect_contributor_page_candidates_from_package(package: dict[str, Any]) -> list[dict[str, Any]]:
    """Repository contributor listing URLs (relationship hints, not person identities)."""
    candidates: list[dict[str, Any]] = []
    package_data = package.get("package") or {}
    links = package_data.get("links") or {}
    if not isinstance(links, dict):
        return candidates
    for key, value in links.items():
        url = _normalize_url(str(value or ""))
        if not url or "github.com" not in url:
            continue
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2:
            repo_url = f"https://github.com/{parts[0]}/{parts[1]}"
            candidates.append(
                {
                    "platform": "github",
                    "handle": f"{parts[0]}/{parts[1]}",
                    "profile_url": f"{repo_url}/graphs/contributors",
                    "evidence_type": "github_contributors_page",
                    "source_field": f"package.links.{key}",
                    "repository_url": repo_url,
                }
            )
    return _dedupe_candidates(candidates)


def collect_person_link_candidates_from_npm(package: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    package_data = package.get("package") or {}
    for maintainer in package_data.get("maintainers") or []:
        if not isinstance(maintainer, dict):
            continue
        username = str(maintainer.get("username") or "").strip()
        if username and _valid_handle(username):
            candidates.append(
                {
                    "platform": "npm",
                    "handle": username,
                    "profile_url": f"https://www.npmjs.com/~{username}",
                    "evidence_type": "npm_maintainer",
                    "source_field": "package.maintainers.username",
                }
            )
        for key in ("url", "homepage"):
            ref = parse_public_profile_url(str(maintainer.get(key) or ""))
            if ref:
                candidates.append(_ref_to_candidate(ref, "package.maintainers." + key))
    links = package_data.get("links") or {}
    if isinstance(links, dict):
        for key, value in links.items():
            ref = parse_public_profile_url(str(value or ""))
            if ref and ref.platform in {"github", "gitlab"}:
                candidates.append(_ref_to_candidate(ref, f"package.links.{key}"))
    return _dedupe_candidates(candidates)


def collect_person_link_candidates_from_pypi(package: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    info = package.get("info") or {}
    project_urls = info.get("project_urls") or {}
    if isinstance(project_urls, dict):
        for key, value in project_urls.items():
            ref = parse_public_profile_url(str(value or ""))
            if ref and ref.platform in {"github", "gitlab", "npm", "pypi"}:
                candidates.append(_ref_to_candidate(ref, f"info.project_urls.{key}"))
    for key in ("package_url", "project_url", "home_page"):
        ref = parse_public_profile_url(str(info.get(key) or ""))
        if ref and ref.platform in {"github", "gitlab", "npm", "pypi"}:
            candidates.append(_ref_to_candidate(ref, f"info.{key}"))
    return _dedupe_candidates(candidates)


def collect_org_link_candidates_from_govuk(result: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for org in result.get("organisations") or []:
        if not isinstance(org, dict):
            continue
        link = str(org.get("link") or "")
        title = str(org.get("title") or "")
        if link.startswith("/government/organisations/"):
            url = f"https://www.gov.uk{link}"
            ref = parse_public_profile_url(url)
            if ref:
                item = _ref_to_candidate(ref, "organisations.link")
                if title:
                    item["display_name"] = title
                candidates.append(item)
    return _dedupe_candidates(candidates)


def _ref_to_candidate(ref: PublicProfileRef, source_field: str) -> dict[str, Any]:
    return {
        "platform": ref.platform,
        "handle": ref.handle,
        "profile_url": ref.profile_url,
        "evidence_type": ref.evidence_type,
        "source_field": source_field,
        "display_name": ref.display_name,
    }


_PLATFORM_PRIORITY = {"github": 0, "gitlab": 1, "npm": 2, "pypi": 3}


def _best_person_refs(refs: list[PublicProfileRef]) -> list[PublicProfileRef]:
    """One preferred public profile per handle (GitHub/GitLab over registry pages)."""
    by_handle: dict[str, PublicProfileRef] = {}
    for ref in refs:
        handle = ref.handle.lower()
        existing = by_handle.get(handle)
        if not existing:
            by_handle[handle] = ref
            continue
        if _PLATFORM_PRIORITY.get(ref.platform, 99) < _PLATFORM_PRIORITY.get(existing.platform, 99):
            by_handle[handle] = ref
    return list(by_handle.values())


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in candidates:
        url = str(item.get("profile_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def extract_person_candidates(profile: dict[str, Any]) -> list[PublicProfileRef]:
    """Extract person profile references from one artifact or signal profile."""
    metadata = profile.get("metadata") or {}
    source = str(metadata.get("source") or "")
    raw = profile.get("raw_signals") or {}
    refs: list[PublicProfileRef] = []

    for candidate in raw.get("person_link_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("profile_url") or "")
        ref = parse_public_profile_url(url)
        if ref:
            refs.append(
                PublicProfileRef(
                    ref.platform,
                    ref.handle,
                    ref.profile_url,
                    str(candidate.get("evidence_type") or ref.evidence_type),
                    str(candidate.get("source_field") or "person_link_candidates"),
                    str(candidate.get("display_name") or ""),
                )
            )

    if source == "public_npm":
        npm_payload = raw.get("npm_search_result") or {}
        for item in collect_person_link_candidates_from_npm(npm_payload if isinstance(npm_payload, dict) else {}):
            refs.append(
                PublicProfileRef(
                    str(item["platform"]),
                    str(item["handle"]),
                    str(item["profile_url"]),
                    str(item["evidence_type"]),
                    str(item["source_field"]),
                )
            )

    if source == "public_pypi":
        pypi_payload = {"info": (raw.get("pypi_info") or {})}
        for item in collect_person_link_candidates_from_pypi(pypi_payload):
            refs.append(
                PublicProfileRef(
                    str(item["platform"]),
                    str(item["handle"]),
                    str(item["profile_url"]),
                    str(item["evidence_type"]),
                    str(item["source_field"]),
                )
            )

    if source in {"public_govuk", "public_spending_context"}:
        gov = raw.get("govuk_result") or raw.get("public_spending_context") or {}
        if isinstance(gov, dict):
            for item in collect_staff_link_candidates_from_govuk(gov):
                refs.append(
                    PublicProfileRef(
                        "govuk",
                        str(item["handle"]),
                        str(item["profile_url"]),
                        "govuk_staff_page",
                        str(item["source_field"]),
                        str(item.get("display_name") or ""),
                    )
                )

    gdelt = raw.get("gdelt_article")
    if isinstance(gdelt, dict):
        for field in ("author", "sourceauthor", "authorurl", "sourceurl"):
            value = str(gdelt.get(field) or "").strip()
            if value.startswith("http"):
                ref = parse_public_profile_url(value)
                if ref and ref.platform in {"github", "gitlab"}:
                    refs.append(
                        PublicProfileRef(ref.platform, ref.handle, ref.profile_url, "gdelt_author_url", f"gdelt_article.{field}")
                    )

    identity = profile.get("identity_anchors") or {}
    direct = parse_public_profile_url(str(identity.get("profile_url") or ""))
    if direct and direct.platform in {"github", "gitlab", "npm", "pypi"}:
        refs.append(direct)

    # Deduplicate by profile URL
    seen_urls: set[str] = set()
    unique: list[PublicProfileRef] = []
    for ref in refs:
        if ref.profile_url in seen_urls:
            continue
        seen_urls.add(ref.profile_url)
        unique.append(ref)
    return unique


def extract_organization_candidates(profile: dict[str, Any]) -> list[PublicProfileRef]:
    metadata = profile.get("metadata") or {}
    source = str(metadata.get("source") or "")
    raw = profile.get("raw_signals") or {}
    refs: list[PublicProfileRef] = []

    if source in {"public_govuk", "public_spending_context"}:
        gov = raw.get("govuk_result") or {}
        if isinstance(gov, dict):
            for item in collect_org_link_candidates_from_govuk(gov):
                refs.append(
                    PublicProfileRef(
                        "govuk",
                        str(item["handle"]),
                        str(item["profile_url"]),
                        "govuk_organisation_page",
                        str(item["source_field"]),
                        str(item.get("display_name") or ""),
                    )
                )

    seen: set[str] = set()
    out: list[PublicProfileRef] = []
    for ref in refs:
        if ref.profile_url in seen:
            continue
        seen.add(ref.profile_url)
        out.append(ref)
    return out


def build_person_profile(
    ref: PublicProfileRef,
    *,
    parent_profile: dict[str, Any],
    derivation_method: str,
) -> dict[str, Any]:
    parent_id = str(parent_profile.get("stratum_id") or "")
    parent_meta = parent_profile.get("metadata") or {}
    collected_at = _utcnow()
    display_name = ref.display_name or ref.handle

    evidence_item = {
        "type": ref.evidence_type,
        "platform": ref.platform,
        "url": ref.profile_url,
        "handle": ref.handle,
        "source_field": ref.source_field,
        "parent_stratum_id": parent_id,
        "parent_source": parent_meta.get("source"),
        "derivation_method": derivation_method,
        "collected_at": collected_at,
    }

    profile = {
        "stratum_id": _stratum_id(),
        "identity_anchors": {
            "handle": ref.handle,
            "platform": ref.platform,
            "display_name": display_name,
            "profile_url": ref.profile_url,
            "resolution_confidence": 0.8,
        },
        "behavioral_intelligence": {
            "digital_activity_score": 0,
            "platform_presence": [ref.platform],
            "public_repos": 0,
            "followers": 0,
            "peak_activity_hours": [],
            "tech_stack": [],
            "contribution_score": 0,
        },
        "situational_intelligence": {
            "country": parent_meta.get("country") or "UK",
            "city": "",
            "region": "",
            "timezone": "",
            "isp": "",
            "org": "",
            "last_signal": collected_at,
        },
        "network_signals": {
            "ip": "",
            "open_ports": [],
            "services": [],
            "hostnames": [],
            "vulnerabilities": [],
        },
        "risk_profile": {
            "overall_risk": "LOW",
            "exposed_services": 0,
            "vulnerability_count": 0,
        },
        "metadata": {
            "source": "derived_public_person",
            "collection_date": collected_at,
            "country": parent_meta.get("country") or "UK",
            "data_type": "public_signal",
            "collection_job_id": parent_meta.get("collection_job_id"),
            "safe_mode": True,
            "derived_from": parent_id,
            "derivation_method": derivation_method,
            "parent_artifact_source": parent_meta.get("source"),
        },
        "raw_signals": {
            "derivation": {
                "parent_stratum_id": parent_id,
                "parent_source": parent_meta.get("source"),
                "method": derivation_method,
                "source_field": ref.source_field,
                "profile_url": ref.profile_url,
            }
        },
        "public_identity_evidence": [evidence_item],
    }
    key = canonical_key_from_public_url(ref.profile_url)
    if key:
        profile["identity_anchors"]["canonical_entity_key"] = key
    return profile


def build_organization_profile(
    ref: PublicProfileRef,
    *,
    parent_profile: dict[str, Any],
) -> dict[str, Any]:
    parent_id = str(parent_profile.get("stratum_id") or "")
    parent_meta = parent_profile.get("metadata") or {}
    collected_at = _utcnow()
    display_name = ref.display_name or ref.handle

    evidence_item = {
        "type": ref.evidence_type,
        "platform": ref.platform,
        "url": ref.profile_url,
        "handle": ref.handle,
        "source_field": ref.source_field,
        "parent_stratum_id": parent_id,
        "parent_source": parent_meta.get("source"),
        "derivation_method": "govuk_organisation",
        "collected_at": collected_at,
    }

    return {
        "stratum_id": _stratum_id(),
        "identity_anchors": {
            "handle": ref.handle,
            "platform": "govuk",
            "display_name": display_name,
            "profile_url": ref.profile_url,
            "resolution_confidence": 0.78,
        },
        "behavioral_intelligence": {
            "digital_activity_score": 10,
            "platform_presence": ["govuk"],
            "public_repos": 0,
            "followers": 0,
            "peak_activity_hours": [],
            "tech_stack": [],
            "contribution_score": 0,
        },
        "situational_intelligence": {
            "country": "UK",
            "city": "",
            "region": "",
            "timezone": "Europe/London",
            "isp": "",
            "org": display_name,
            "last_signal": collected_at,
        },
        "network_signals": {
            "ip": "",
            "open_ports": [],
            "services": [],
            "hostnames": ["www.gov.uk"],
            "vulnerabilities": [],
        },
        "risk_profile": {
            "overall_risk": "LOW",
            "exposed_services": 0,
            "vulnerability_count": 0,
        },
        "metadata": {
            "source": "derived_public_organization",
            "collection_date": collected_at,
            "country": "UK",
            "data_type": "public_signal",
            "collection_job_id": parent_meta.get("collection_job_id"),
            "safe_mode": True,
            "derived_from": parent_id,
            "derivation_method": "govuk_organisation",
            "parent_artifact_source": parent_meta.get("source"),
        },
        "raw_signals": {
            "derivation": {
                "parent_stratum_id": parent_id,
                "parent_source": parent_meta.get("source"),
                "method": "govuk_organisation",
                "profile_url": ref.profile_url,
            }
        },
        "public_identity_evidence": [evidence_item],
    }


def derive_person_profiles(profiles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Append derived person/org profiles from artifact rows. Original profiles are preserved.
    """
    derived_persons: list[dict[str, Any]] = []
    derived_orgs: list[dict[str, Any]] = []
    artifacts_with_hints = 0
    skipped_no_url = 0
    seen_person_urls: set[str] = set()
    seen_org_urls: set[str] = set()

    existing_urls: set[str] = set()
    for profile in profiles:
        meta = profile.get("metadata") or {}
        source = str(meta.get("source") or "")
        if source not in {"public_github", "public_gitlab", "derived_public_person"}:
            continue
        identity = profile.get("identity_anchors") or {}
        url = _normalize_url(str(identity.get("profile_url") or ""))
        if url:
            existing_urls.add(url)

    for profile in profiles:
        meta = profile.get("metadata") or {}
        source = str(meta.get("source") or "")
        if source in {"public_github", "public_gitlab", "derived_public_person"}:
            continue

        person_refs = _best_person_refs(extract_person_candidates(profile))
        if person_refs:
            artifacts_with_hints += 1

        for ref in person_refs:
            if ref.profile_url in seen_person_urls or ref.profile_url in existing_urls:
                continue
            if ref.platform not in {"github", "gitlab", "npm", "pypi", "govuk"}:
                continue
            if ref.platform == "govuk" and ref.evidence_type != "govuk_staff_page":
                continue
            seen_person_urls.add(ref.profile_url)
            method = f"{source}_person_link" if source else "artifact_person_link"
            derived_persons.append(
                build_person_profile(ref, parent_profile=profile, derivation_method=method)
            )

        if source in {"public_govuk", "public_spending_context"}:
            for ref in extract_organization_candidates(profile):
                if ref.profile_url in seen_org_urls:
                    continue
                seen_org_urls.add(ref.profile_url)
                derived_orgs.append(build_organization_profile(ref, parent_profile=profile))

        if source in {"public_npm", "public_pypi"} and not person_refs:
            skipped_no_url += 1

    combined = list(profiles) + derived_persons + derived_orgs
    report = {
        "generated_at": _utcnow(),
        "input_profiles": len(profiles),
        "persons_derived": len(derived_persons),
        "organizations_derived": len(derived_orgs),
        "artifacts_with_person_hints": artifacts_with_hints,
        "skipped_artifacts_without_verifiable_person_url": skipped_no_url,
        "total_after_derivation": len(combined),
    }
    return combined, report
