"""Canonical entity resolution helpers for public STRATUM profiles.

The resolver is deterministic and local: it does not invent entities or create
new profiles. It only normalizes anchors already present in public-source
signals so collectors and exports can deduplicate/enrich consistently.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlparse


_SPACE_RE = re.compile(r"\s+")
_SAFE_KEY_RE = re.compile(r"[^a-z0-9._:-]+")
_UK_SECOND_LEVELS = {"ac", "co", "gov", "ltd", "me", "net", "nhs", "org", "plc", "police", "sch"}
_GENERIC_HOSTS = {
    "api.github.com",
    "github.com",
    "gitlab.com",
    "npmjs.com",
    "pypi.org",
    "registry.npmjs.org",
    "www.gov.uk",
}


@dataclass(frozen=True)
class CanonicalResolution:
    canonical_entity_key: str
    canonical_entity_hash: str
    canonical_name: str
    entity_type: str
    resolution_confidence: float
    match_strategy: str
    normalized_anchors: dict[str, Any]
    aliases: list[str]


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = _SPACE_RE.sub(" ", text)
    return text


def normalize_key_part(value: Any, fallback: str = "unknown") -> str:
    text = normalize_text(value)
    text = text.replace(" ", "-")
    text = _SAFE_KEY_RE.sub("-", text).strip("-._:")
    return text or fallback


def normalize_handle(value: Any) -> str:
    text = normalize_text(value)
    text = text.removeprefix("@")
    text = text.replace("https://", "").replace("http://", "")
    return normalize_key_part(text)


def normalize_domain(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    host = host.lower().split("@")[-1].split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def registered_domain(hostname: Any) -> str:
    host = normalize_domain(hostname)
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    if parts[-1] == "uk" and parts[-2] in _UK_SECOND_LEVELS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def canonical_key_from_public_url(url: str) -> str | None:
    """Map an allowlisted public profile URL to a canonical entity key (no external imports)."""
    raw = str(url or "").strip()
    if not raw:
        return None
    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    parts = [segment for segment in parsed.path.split("/") if segment]
    _gh_reserved = {"settings", "orgs", "organizations", "topics", "login", "signup", "explore"}
    if host in {"github.com", "www.github.com"} and parts and parts[0] not in _gh_reserved:
        login = normalize_handle(parts[0])
        if login:
            return f"developer:github:{login}"
    if host in {"gitlab.com", "www.gitlab.com"} and parts:
        login = normalize_handle(parts[0])
        if login:
            return f"developer:gitlab:{login}"
    if host in {"www.npmjs.com", "npmjs.com"} and len(parts) >= 2 and parts[0] == "~":
        login = normalize_handle(parts[1])
        if login:
            return f"developer:npm:{login}"
    if host in {"pypi.org", "www.pypi.org"} and len(parts) >= 2 and parts[0] == "user":
        login = normalize_handle(parts[1])
        if login:
            return f"developer:pypi:{login}"
    if host in {"www.gov.uk", "gov.uk"} and len(parts) >= 3 and parts[0] == "government" and parts[1] == "organisations":
        return f"organization:{normalize_key_part(parts[2])}"
    if host in {"www.gov.uk", "gov.uk"} and len(parts) >= 3 and parts[0] == "government" and parts[1] == "people":
        return f"person:govuk:{normalize_key_part(parts[2])}"
    return None


def source_url(profile: dict[str, Any]) -> str:
    identity = profile.get("identity_anchors") or {}
    raw = profile.get("raw_signals") or {}
    profile_url = str(identity.get("profile_url") or "")
    if profile_url:
        return profile_url

    for key in ("govuk_result", "public_spending_context", "gdelt_article"):
        payload = raw.get(key)
        if not isinstance(payload, dict):
            continue
        link = str(payload.get("link") or payload.get("url") or payload.get("profile_url") or "")
        if link.startswith("/"):
            return f"https://www.gov.uk{link}"
        if link:
            return link
    return ""


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _title_hash(value: Any) -> str:
    return hashlib.sha256(normalize_text(value).encode("utf-8")).hexdigest()[:12]


def _org_from_profile(profile: dict[str, Any]) -> str:
    situational = profile.get("situational_intelligence") or {}
    org = normalize_text(situational.get("org"))
    if org and org not in {"openstreetmap", "none", "unknown"}:
        return org
    return ""


def _profile_hostnames(profile: dict[str, Any]) -> list[str]:
    network = profile.get("network_signals") or {}
    hosts = []
    for host in network.get("hostnames") or []:
        normalized = normalize_domain(host)
        if normalized:
            hosts.append(normalized)
    url = source_url(profile)
    host = normalize_domain(url)
    if host:
        hosts.append(host)
    return list(dict.fromkeys(hosts))


def _resolution_candidates(profile: dict[str, Any]) -> tuple[str, str, str, float, str]:
    identity = profile.get("identity_anchors") or {}
    metadata = profile.get("metadata") or {}
    platform = normalize_key_part(identity.get("platform"))
    source = normalize_key_part(metadata.get("source"))
    handle = normalize_handle(identity.get("handle"))
    org = _org_from_profile(profile)
    url = source_url(profile)
    url_hash = _title_hash(url) if url else ""
    hostnames = _profile_hostnames(profile)
    domains = [registered_domain(host) for host in hostnames if registered_domain(host)]
    non_generic_domains = [domain for domain in domains if domain not in _GENERIC_HOSTS]

    osm_id = normalize_key_part(identity.get("osm_id"), "")
    if platform == "openstreetmap" and osm_id:
        return f"place:{osm_id}", str(identity.get("handle") or osm_id), "place", 0.92, "osm_id"

    if platform == "domain" and handle:
        domain = registered_domain(handle)
        return f"domain:{domain}", domain, "domain", 0.9, "domain_handle"

    if non_generic_domains and platform in {"hostname", "domain"}:
        domain = non_generic_domains[0]
        return f"domain:{domain}", domain, "domain", 0.88, "network_domain"

    if platform in {"github", "gitlab"} and handle:
        return f"developer:{platform}:{handle}", str(identity.get("handle") or handle), "digital_identity", 0.84, "public_platform_handle"

    if platform == "npm" and handle and source in {"derived_public_person"}:
        return f"developer:npm:{handle}", str(identity.get("handle") or handle), "digital_identity", 0.8, "npm_maintainer_page"

    if platform == "pypi" and handle and source in {"derived_public_person"}:
        return f"developer:pypi:{handle}", str(identity.get("handle") or handle), "digital_identity", 0.8, "pypi_author_page"

    if platform in {"npm", "pypi"} and handle:
        return f"package:{platform}:{handle}", str(identity.get("handle") or handle), "software_artifact", 0.82, "package_registry_handle"

    if source == "public_spending_context":
        if org:
            return f"organization:{normalize_key_part(org)}", org, "organization", 0.8, "public_spending_org"
        if url_hash:
            return f"public-record:spending:{url_hash}", str(identity.get("handle") or url), "public_record", 0.72, "public_spending_url"

    if source == "public_govuk":
        if "/government/people/" in url:
            slug = normalize_key_part(handle) or normalize_key_part(url.split("/government/people/")[-1].split("/")[0])
            return f"person:govuk:{slug}", str(identity.get("display_name") or handle or slug), "digital_identity", 0.8, "govuk_staff_page"
        if org:
            return f"organization:{normalize_key_part(org)}", org, "organization", 0.78, "govuk_org"
        if url_hash:
            return f"public-record:govuk:{url_hash}", str(identity.get("handle") or url), "public_record", 0.7, "govuk_url"

    if source == "public_gdelt" and url_hash:
        host = normalize_domain(url)
        if host and host not in _GENERIC_HOSTS:
            return f"publisher:{registered_domain(host)}", registered_domain(host), "publisher", 0.76, "gdelt_publisher_domain"
        return f"public-record:gdelt:{url_hash}", str(identity.get("handle") or url), "public_record", 0.66, "gdelt_url"

    if non_generic_domains:
        domain = non_generic_domains[0]
        return f"domain:{domain}", domain, "domain", 0.74, "url_domain"

    if handle:
        return f"{platform}:{handle}", str(identity.get("handle") or handle), "public_profile", 0.6, "platform_handle"

    fallback = _title_hash(profile.get("stratum_id") or source or platform)
    return f"unresolved:{source}:{fallback}", str(identity.get("handle") or fallback), "unknown", 0.35, "fallback_hash"


def resolve_profile(profile: dict[str, Any]) -> CanonicalResolution:
    identity = profile.get("identity_anchors") or {}
    metadata = profile.get("metadata") or {}
    canonical_key, canonical_name, entity_type, confidence, strategy = _resolution_candidates(profile)
    hosts = _profile_hostnames(profile)
    aliases = list(
        dict.fromkeys(
            item
            for item in [
                str(identity.get("handle") or "").strip(),
                str(identity.get("display_name") or "").strip(),
                canonical_name,
                _org_from_profile(profile),
                *hosts,
            ]
            if item
        )
    )
    normalized_anchors = {
        "handle": normalize_handle(identity.get("handle")),
        "platform": normalize_key_part(identity.get("platform")),
        "source": normalize_key_part(metadata.get("source")),
        "org": normalize_key_part(_org_from_profile(profile), ""),
        "domains": list(dict.fromkeys(registered_domain(host) for host in hosts if registered_domain(host))),
        "source_url": source_url(profile),
    }
    return CanonicalResolution(
        canonical_entity_key=canonical_key,
        canonical_entity_hash=_hash_key(canonical_key),
        canonical_name=canonical_name,
        entity_type=entity_type,
        resolution_confidence=round(min(0.99, max(0.0, confidence)), 2),
        match_strategy=strategy,
        normalized_anchors=normalized_anchors,
        aliases=aliases[:12],
    )


def apply_canonical_resolution(profile: dict[str, Any]) -> dict[str, Any]:
    resolution = resolve_profile(profile)
    identity = profile.setdefault("identity_anchors", {})
    existing_confidence = float(identity.get("resolution_confidence") or 0)
    identity["canonical_entity_key"] = resolution.canonical_entity_key
    identity["canonical_entity_hash"] = resolution.canonical_entity_hash
    identity["canonical_name"] = resolution.canonical_name
    identity["entity_type"] = resolution.entity_type
    identity["normalized_handle"] = resolution.normalized_anchors.get("handle")
    identity["resolution_confidence"] = round(max(existing_confidence, resolution.resolution_confidence), 2)
    profile["entity_resolution"] = asdict(resolution)
    return profile
