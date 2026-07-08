"""
STRATUM Entity Resolution Service

Canonical entity keys, deduplication, cross-source matching, alias resolution,
confidence scoring. Deterministic, local-only (no external APIs).

Entity types supported:
  - person: Individual human
  - organization: Company, nonprofit, government agency
  - publisher: News outlet, blog platform, publication
  - public_record: Court record, government filing, regulatory record
  - domain: Website domain or online property
  - institution: University, research organization, educational institution
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────────────────
# NORMALIZATION UTILITIES
# ─────────────────────────────────────────────────────────────────────────

_SPACE_RE = re.compile(r"\s+")
_SAFE_KEY_RE = re.compile(r"[^a-z0-9._:-]+")
_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$", re.IGNORECASE)
_URL_RE = re.compile(
    r"https?://(?:www\.)?([a-z0-9.-]+\.(?:[a-z]{2,}|[a-z]{2}\.[a-z]{2}))", re.IGNORECASE
)
_UK_SECOND_LEVELS = {"ac", "co", "gov", "ltd", "me", "net", "nhs", "org", "plc", "police", "sch"}
_COMMON_TECH_DOMAINS = {
    "github.com", "gitlab.com", "bitbucket.org", "sourceforge.net",
    "npm.com", "npmjs.com", "registry.npmjs.org",
    "pypi.org", "pypi.python.org",
    "stackexchange.com", "stackoverflow.com",
    "twitter.com", "x.com", "linkedin.com", "facebook.com",
    "reddit.com", "medium.com",
}


def normalize_text(value: Any) -> str:
    """Unicode normalization, lowercase, space collapsing."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = _SPACE_RE.sub(" ", text)
    return text


def normalize_key_part(value: Any, fallback: str = "unknown") -> str:
    """Safe key component: alphanumeric, hyphens, dots, colons."""
    text = normalize_text(value)
    text = text.replace(" ", "-")
    text = _SAFE_KEY_RE.sub("-", text).strip("-._:")
    return text or fallback


def normalize_handle(value: Any) -> str:
    """Social media handle: remove @, URL prefixes, normalize."""
    text = normalize_text(value)
    text = text.removeprefix("@")
    text = text.replace("https://", "").replace("http://", "").replace("www.", "")
    return normalize_key_part(text)


def normalize_email(value: Any) -> str:
    """Email: lowercase, validate format."""
    email = str(value or "").strip().lower()
    if _EMAIL_RE.match(email):
        return email
    return ""


def normalize_domain(value: Any) -> str:
    """Domain: extract from URL if needed, normalize, remove www."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    
    # Extract domain from URL
    candidate = raw if "://" in raw else f"https://{raw}"
    try:
        parsed = urlparse(candidate)
        host = parsed.netloc or parsed.path.split("/", 1)[0]
    except Exception:
        host = raw
    
    host = host.lower().split("@")[-1].split(":")[0].strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def normalize_phone(value: Any) -> str:
    """Phone: keep only digits and +."""
    text = str(value or "")
    text = re.sub(r"[^\d+]", "", text)
    return text if len(text) >= 7 else ""


def registered_domain(hostname: Any) -> str:
    """Extract registered domain (e.g., github.com from api.github.com)."""
    host = normalize_domain(hostname)
    parts = [part for part in host.split(".") if part]
    
    if len(parts) <= 2:
        return host
    
    # Handle UK second-level domains (.co.uk, .gov.uk, etc.)
    if parts[-1] == "uk" and parts[-2] in _UK_SECOND_LEVELS and len(parts) >= 3:
        return ".".join(parts[-3:])
    
    return ".".join(parts[-2:])


def normalize_name(value: Any) -> str:
    """Person/org name: normalize but preserve structure."""
    text = normalize_text(value)
    # Remove titles, prefixes
    for prefix in ("mr.", "mrs.", "ms.", "dr.", "prof.", "sir", "lady"):
        if text.startswith(prefix + " "):
            text = text[len(prefix)+1:].strip()
            break
    return text


# ─────────────────────────────────────────────────────────────────────────
# HASHING & FINGERPRINTING
# ─────────────────────────────────────────────────────────────────────────

def _hash_text(value: str) -> str:
    """SHA256 hash, first 16 chars."""
    if not value:
        return "0000000000000000"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _hash_email(email: str) -> str:
    """Hash email address for matching."""
    normalized = normalize_email(email)
    if not normalized:
        return ""
    return _hash_text(normalized)


def _hash_domain(domain: str) -> str:
    """Hash registered domain for matching."""
    normalized = registered_domain(domain)
    if not normalized:
        return ""
    return _hash_text(normalized)


def _phonetic_hash(name: str) -> str:
    """Metaphone-like hash for fuzzy name matching (simplified)."""
    name = normalize_name(name)
    if len(name) < 2:
        return ""
    # Simple phonetic: first 3 chars + vowel removal
    consonants = "".join(ch for ch in name if ch not in "aeiouoy")
    return (name[:3] + consonants[:3])[:6]


# ─────────────────────────────────────────────────────────────────────────
# ENTITY TYPES & RESOLUTION RESULTS
# ─────────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    PERSON = "person"
    ORGANIZATION = "organization"
    PUBLISHER = "publisher"
    PUBLIC_RECORD = "public_record"
    DOMAIN = "domain"
    INSTITUTION = "institution"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CanonicalEntity:
    """Resolved canonical entity with all evidence."""
    canonical_entity_key: str
    canonical_entity_hash: str
    primary_identifier: str
    entity_type: EntityType
    confidence: float
    match_strategy: str
    resolution_count: int  # How many source records matched
    normalized_anchors: dict[str, Any]
    aliases: list[str] = field(default_factory=list)
    related_domains: list[str] = field(default_factory=list)
    related_emails: list[str] = field(default_factory=list)
    related_handles: list[tuple[str, str]] = field(default_factory=list)  # (platform, handle)
    evidence: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DuplicateMatch:
    """Two profiles matched as likely duplicates."""
    profile_id_1: str
    profile_id_2: str
    match_confidence: float
    match_reason: str
    match_evidence: list[str]


# ─────────────────────────────────────────────────────────────────────────
# ENTITY RESOLUTION ENGINE
# ─────────────────────────────────────────────────────────────────────────

class EntityResolutionEngine:
    """
    Deterministic, local-only entity resolution.
    
    Does NOT:
    - Call external APIs
    - Create new profiles
    - Invent identities
    
    DOES:
    - Normalize anchors from public signals
    - Deduplicate profiles by canonical keys
    - Score confidence from evidence count
    - Support cross-source matching
    - Preserve all provenance
    """
    
    def __init__(self):
        self._canonical_cache: dict[str, CanonicalEntity] = {}
        self._profile_to_canonical: dict[str, str] = {}
    
    def infer_entity_type(self, profile: dict[str, Any]) -> EntityType:
        """Infer entity type from profile signals."""
        identity = profile.get("identity_anchors") or {}
        metadata = profile.get("metadata") or {}
        source = str(metadata.get("source") or "")
        
        # Platform hints
        if "github" in source or "gitlab" in source or "npm" in source or "pypi" in source:
            return EntityType.PERSON  # Tech person
        
        if "company" in source.lower() or "organization" in source.lower():
            return EntityType.ORGANIZATION
        
        if "publisher" in source.lower() or "gdelt" in source:
            return EntityType.PUBLISHER
        
        if "court" in source.lower() or "record" in source.lower() or "filing" in source.lower():
            return EntityType.PUBLIC_RECORD
        
        if "domain" in source.lower() or "whois" in source.lower():
            return EntityType.DOMAIN
        
        if "university" in source.lower() or "institution" in source.lower() or "academic" in source.lower():
            return EntityType.INSTITUTION
        
        return EntityType.UNKNOWN
    
    def resolve_profile(
        self,
        profile: dict[str, Any],
        entity_type: Optional[EntityType] = None,
    ) -> CanonicalEntity:
        """
        Resolve a single profile to canonical entity.
        
        Uses profile's identity_anchors to build canonical key.
        """
        identity = profile.get("identity_anchors") or {}
        metadata = profile.get("metadata") or {}
        
        entity_type = entity_type or self.infer_entity_type(profile)
        
        # Build normalized anchors
        normalized = {
            "handle": normalize_handle(identity.get("handle")),
            "email": normalize_email(identity.get("email")),
            "domain": normalize_domain(identity.get("domain")),
            "name": normalize_name(identity.get("display_name", identity.get("name", ""))),
            "platform": normalize_key_part(identity.get("platform")),
            "profile_url": normalize_domain(identity.get("profile_url")),
        }
        
        # Remove empty values
        normalized = {k: v for k, v in normalized.items() if v}
        
        # Build canonical key based on entity type
        if entity_type == EntityType.PERSON:
            key = self._person_canonical_key(normalized)
        elif entity_type == EntityType.DOMAIN:
            key = self._domain_canonical_key(normalized)
        elif entity_type == EntityType.ORGANIZATION:
            key = self._organization_canonical_key(normalized)
        else:
            key = self._generic_canonical_key(normalized, entity_type)
        
        # Hashes for matching
        entity_hash = _hash_text(key)
        
        # Collect aliases
        aliases = []
        if normalized.get("handle"):
            aliases.append(normalized["handle"])
        if normalized.get("name"):
            aliases.append(normalized["name"])
        
        # Related info
        related_domains = [normalized["domain"]] if normalized.get("domain") else []
        if normalized.get("profile_url"):
            related_domains.append(normalized["profile_url"])
        
        related_emails = [normalized["email"]] if normalized.get("email") else []
        
        related_handles = []
        if normalized.get("handle") and normalized.get("platform"):
            related_handles.append((normalized["platform"], normalized["handle"]))
        
        # Evidence
        evidence = [
            {
                "type": "source",
                "value": metadata.get("source"),
                "timestamp": metadata.get("collection_date"),
            }
        ]
        
        confidence = self._calculate_confidence(normalized, entity_type)
        
        entity = CanonicalEntity(
            canonical_entity_key=key,
            canonical_entity_hash=entity_hash,
            primary_identifier=normalized.get("handle") or normalized.get("name") or key,
            entity_type=entity_type,
            confidence=confidence,
            match_strategy=self._match_strategy_name(entity_type, normalized),
            resolution_count=1,
            normalized_anchors=normalized,
            aliases=aliases,
            related_domains=list(dict.fromkeys(related_domains)),
            related_emails=list(dict.fromkeys(related_emails)),
            related_handles=list(dict.fromkeys(related_handles)),
            evidence=evidence,
        )
        
        self._canonical_cache[key] = entity
        return entity
    
    def match_profiles(
        self,
        profile1: dict[str, Any],
        profile2: dict[str, Any],
    ) -> Optional[DuplicateMatch]:
        """
        Compare two profiles for matching/duplication.
        
        Returns DuplicateMatch if they likely represent the same entity.
        """
        id1 = str(profile1.get("stratum_id") or "")
        id2 = str(profile2.get("stratum_id") or "")
        
        if not id1 or not id2 or id1 == id2:
            return None
        
        identity1 = profile1.get("identity_anchors") or {}
        identity2 = profile2.get("identity_anchors") or {}
        
        # Collect matching signals
        signals = []
        reasons = []
        
        # Exact handle match on same platform
        handle1 = normalize_handle(identity1.get("handle"))
        handle2 = normalize_handle(identity2.get("handle"))
        platform1 = normalize_key_part(identity1.get("platform"))
        platform2 = normalize_key_part(identity2.get("platform"))
        
        if handle1 and handle1 == handle2 and platform1 == platform2:
            signals.append("exact_handle_platform")
            reasons.append(f"Same {platform1} handle: {handle1}")
        
        # Email match
        email1 = normalize_email(identity1.get("email"))
        email2 = normalize_email(identity2.get("email"))
        
        if email1 and email1 == email2:
            signals.append("exact_email")
            reasons.append(f"Same email: {email1}")
        
        # Domain match
        domain1 = normalize_domain(identity1.get("domain"))
        domain2 = normalize_domain(identity2.get("domain"))
        
        if domain1 and domain1 == domain2:
            signals.append("exact_domain")
            reasons.append(f"Same domain: {domain1}")
        
        # URL match
        url1 = normalize_domain(identity1.get("profile_url"))
        url2 = normalize_domain(identity2.get("profile_url"))
        
        if url1 and url1 == url2:
            signals.append("exact_profile_url")
            reasons.append(f"Same profile URL: {url1}")
        
        # Name match (phonetic)
        name1 = normalize_name(identity1.get("display_name", identity1.get("name", "")))
        name2 = normalize_name(identity2.get("display_name", identity2.get("name", "")))
        
        if name1 and name1 == name2 and len(name1) > 3:
            signals.append("exact_name")
            reasons.append(f"Same name: {name1}")
        
        # Partial handle match (username + different platform)
        if handle1 and handle1 == handle2 and platform1 != platform2:
            signals.append("same_handle_different_platform")
            reasons.append(f"Same handle on different platforms: {handle1}")
        
        # Calculate match confidence
        if not signals:
            return None
        
        # Score: each exact match is high confidence
        confidence = min(0.99, 0.70 + len(signals) * 0.10)
        
        return DuplicateMatch(
            profile_id_1=id1,
            profile_id_2=id2,
            match_confidence=confidence,
            match_reason=" + ".join(signals),
            match_evidence=reasons,
        )
    
    def deduplicate_profiles(
        self,
        profiles: list[dict[str, Any]],
        confidence_threshold: float = 0.80,
    ) -> tuple[list[list[str]], dict[str, DuplicateMatch]]:
        """
        Group profiles into potential duplicates.
        
        Returns:
          - groups: List of [profile_ids] that are likely duplicates
          - matches: Map of "id1+id2" -> DuplicateMatch
        """
        matches: dict[str, DuplicateMatch] = {}
        groups: dict[str, set[str]] = {}  # canonical_key -> set of profile_ids
        
        # Build groups by canonical key
        for profile in profiles:
            try:
                entity = self.resolve_profile(profile)
                profile_id = str(profile.get("stratum_id") or "")
                
                if profile_id:
                    if entity.canonical_entity_key not in groups:
                        groups[entity.canonical_entity_key] = set()
                    groups[entity.canonical_entity_key].add(profile_id)
            except Exception:
                continue
        
        # Find pairwise duplicates within groups
        for group_ids in groups.values():
            group_list = list(group_ids)
            for i in range(len(group_list)):
                for j in range(i + 1, len(group_list)):
                    profile_i = next(
                        (p for p in profiles if p.get("stratum_id") == group_list[i]),
                        None,
                    )
                    profile_j = next(
                        (p for p in profiles if p.get("stratum_id") == group_list[j]),
                        None,
                    )
                    
                    if profile_i and profile_j:
                        match = self.match_profiles(profile_i, profile_j)
                        if match and match.match_confidence >= confidence_threshold:
                            key = f"{group_list[i]}+{group_list[j]}"
                            matches[key] = match
        
        # Return deduplicated groups and matches
        return [list(ids) for ids in groups.values()], matches
    
    # Private helper methods
    
    def _person_canonical_key(self, normalized: dict[str, str]) -> str:
        """Build canonical key for person."""
        parts = []
        
        if normalized.get("handle"):
            parts.append(f"@{normalized['handle']}")
        if normalized.get("platform"):
            parts.append(f":{normalized['platform']}")
        if normalized.get("email"):
            parts.append(f"<{normalized['email']}>")
        if normalized.get("name"):
            parts.append(f"~{normalized['name']}")
        
        key = "-".join(parts) if parts else "person-unknown"
        return _hash_text(key)
    
    def _domain_canonical_key(self, normalized: dict[str, str]) -> str:
        """Build canonical key for domain."""
        domain = normalized.get("domain") or normalized.get("profile_url")
        if domain:
            domain = registered_domain(domain)
        return f"domain-{domain}" if domain else "domain-unknown"
    
    def _organization_canonical_key(self, normalized: dict[str, str]) -> str:
        """Build canonical key for organization."""
        parts = []
        if normalized.get("name"):
            parts.append(normalized["name"])
        if normalized.get("domain"):
            parts.append(normalized["domain"])
        
        key = ":".join(parts) if parts else "org-unknown"
        return f"org-{_hash_text(key)}"
    
    def _generic_canonical_key(self, normalized: dict[str, str], entity_type: EntityType) -> str:
        """Build generic canonical key."""
        identifier = (
            normalized.get("handle") or
            normalized.get("name") or
            normalized.get("email") or
            normalized.get("domain") or
            "unknown"
        )
        return f"{entity_type.value}-{_hash_text(identifier)}"
    
    def _match_strategy_name(self, entity_type: EntityType, normalized: dict[str, str]) -> str:
        """Describe the matching strategy used."""
        if entity_type == EntityType.PERSON:
            if normalized.get("email"):
                return "email_primary"
            if normalized.get("handle") and normalized.get("platform"):
                return "platform_handle"
            if normalized.get("name"):
                return "name_phonetic"
        elif entity_type == EntityType.DOMAIN:
            return "domain_registered"
        elif entity_type == EntityType.ORGANIZATION:
            return "organization_name_domain"
        
        return "generic"
    
    def _calculate_confidence(self, normalized: dict[str, str], entity_type: EntityType) -> float:
        """Calculate resolution confidence based on available anchors."""
        confidence = 0.50  # Base
        
        # More anchors = higher confidence
        anchor_count = sum(1 for v in normalized.values() if v)
        confidence += min(0.30, anchor_count * 0.08)
        
        # Email = very high confidence
        if normalized.get("email"):
            confidence += 0.10
        
        # Domain + platform = high confidence
        if normalized.get("domain") and normalized.get("platform"):
            confidence += 0.08
        
        # URL = moderate confidence
        if normalized.get("profile_url"):
            confidence += 0.05
        
        return min(0.99, confidence)


# ─────────────────────────────────────────────────────────────────────────
# SINGLETON INSTANCE
# ─────────────────────────────────────────────────────────────────────────

_engine: Optional[EntityResolutionEngine] = None


def get_engine() -> EntityResolutionEngine:
    """Get or create the entity resolution engine."""
    global _engine
    if _engine is None:
        _engine = EntityResolutionEngine()
    return _engine


def resolve_profile(profile: dict[str, Any]) -> CanonicalEntity:
    """Convenience function to resolve a profile."""
    return get_engine().resolve_profile(profile)


def find_duplicates(profiles: list[dict[str, Any]]) -> tuple[list[list[str]], dict[str, DuplicateMatch]]:
    """Convenience function to find duplicates."""
    return get_engine().deduplicate_profiles(profiles)
