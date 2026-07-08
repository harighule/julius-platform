"""
STRATUM Profile Enricher Service

Calculates derived scores from real collected signals:
  - public_social_activity_score: Platform presence, followers, repos
  - public_digital_pattern_score: Activity consistency, frequency
  - public_spending_context_score: Government/business entity indicators
  - source_diversity_score: Multiple sources + categories
  - entity_trust_score: Verification signals + evidence count
  - behavioral_pattern_score: Consistency across platforms
  - activity_consistency_score: Temporal patterns
  - signal_strength_score: Overall signal quality

All scores: 0-100 scale, based on evidence not synthetic data.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from datetime import datetime, timezone
from collections import Counter
from .contact_enrichment import extract_contact_from_profile

logger = logging.getLogger(__name__)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SCORE CALCULATORS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ProfileEnricher:
    """Calculates enrichment scores from real signals."""
    
    def __init__(self):
        pass
    
    def enrich(self, profile: dict[str, Any]) -> dict[str, Any]:
        """
        Enrich a profile with all derived scores.
        
        Adds/updates derived_signals with all calculated scores.
        """
        profile = dict(profile)  # Make a copy
        
        # Calculate all scores
        social_activity = self.calculate_social_activity_score(profile)
        digital_pattern = self.calculate_digital_pattern_score(profile)
        spending_context = self.calculate_spending_context_score(profile)
        source_diversity = self.calculate_source_diversity_score(profile)
        entity_trust = self.calculate_entity_trust_score(profile)
        behavioral_pattern = self.calculate_behavioral_pattern_score(profile)
        activity_consistency = self.calculate_activity_consistency_score(profile)
        signal_strength = self.calculate_signal_strength_score(profile)
        
        # Aggregate into derived_signals
        derived_signals = profile.get("derived_signals", {})
        derived_signals.update({
            "public_social_activity_score": social_activity,
            "public_digital_pattern_score": digital_pattern,
            "public_spending_context_score": spending_context,
            "source_diversity_score": source_diversity,
            "entity_trust_score": entity_trust,
            "behavioral_pattern_score": behavioral_pattern,
            "activity_consistency_score": activity_consistency,
            "signal_strength_score": signal_strength,
        })
        
        # Calculate overall confidence/quality
        overall_confidence = self._calculate_overall_confidence(
            social_activity,
            digital_pattern,
            spending_context,
            source_diversity,
            entity_trust,
            behavioral_pattern,
            activity_consistency,
            signal_strength,
        )
        derived_signals["overall_confidence"] = overall_confidence
        
        profile["derived_signals"] = derived_signals
        
        # Update timestamp
        if "metadata" not in profile:
            profile["metadata"] = {}
        profile["metadata"]["enriched_at"] = datetime.now(timezone.utc).isoformat()
        
        return profile
    
    def calculate_social_activity_score(self, profile: dict[str, Any]) -> int:
        """
        Social activity score: 0-100
        
        Based on:
          - Followers count
          - Public repos count
          - Platform presence count
          - Contribution score
        """
        behavioral = profile.get("behavioral_intelligence", {})
        
        score = 0
        
        # Followers: 0-25 points
        followers = int(behavioral.get("followers", 0))
        if followers > 0:
            score += min(25, 5 + followers // 20)
        
        # Public repos: 0-25 points
        repos = int(behavioral.get("public_repos", 0))
        if repos > 0:
            score += min(25, 5 + repos // 5)
        
        # Platforms: 0-25 points
        platforms = behavioral.get("platform_presence", [])
        if isinstance(platforms, list):
            platform_count = len([p for p in platforms if p])
            score += min(25, platform_count * 8)
        
        # Contribution score: 0-25 points
        contribution = int(behavioral.get("contribution_score", 0))
        if contribution > 0:
            score += min(25, contribution // 4)
        
        return min(100, score)
    
    def calculate_digital_pattern_score(self, profile: dict[str, Any]) -> int:
        """
        Digital pattern score: 0-100
        
        Based on:
          - Activity score from behavioral data
          - Tech stack diversity
          - Domain/website presence
          - Consistency of presence
        """
        behavioral = profile.get("behavioral_intelligence", {})
        identity = profile.get("identity_anchors", {})
        network = profile.get("network_signals", {})
        
        score = 0
        
        # Activity score: 0-30 points
        activity = int(behavioral.get("digital_activity_score", 0))
        if activity > 0:
            score += min(30, activity // 3)
        
        # Tech stack diversity: 0-25 points
        tech_stack = behavioral.get("tech_stack", [])
        if isinstance(tech_stack, list):
            tech_count = len([t for t in tech_stack if t])
            score += min(25, tech_count * 5)
        
        # Domain presence: 0-25 points
        domains = set()
        if identity.get("domain"):
            domains.add(identity["domain"])
        if identity.get("profile_url"):
            domains.add(identity["profile_url"])
        
        hostnames = network.get("hostnames", [])
        if isinstance(hostnames, list):
            domains.update([h for h in hostnames if h])
        
        if domains:
            score += min(25, len(domains) * 8)
        
        # Platform consistency: 0-20 points
        platforms = behavioral.get("platform_presence", [])
        if isinstance(platforms, list) and len(platforms) >= 2:
            score += min(20, len(platforms) * 7)
        
        return min(100, score)
    
    def calculate_spending_context_score(self, profile: dict[str, Any]) -> int:
        """
        Spending/business context score: 0-100
        
        Based on:
          - Government/official datasets
          - Public spending/contract data
          - Corporate registrations
          - Institutional affiliations
        """
        raw_signals = profile.get("raw_signals", {})
        metadata = profile.get("metadata", {})
        source = str(metadata.get("source", ""))
        
        score = 0
        
        # Government dataset signals: 0-35 points
        if "govuk" in source or "public_spending" in source or "spending_context" in raw_signals:
            score += 35
        elif any(x in source for x in ["government", "public", "official"]):
            score += 20
        
        # Corporate/registration signals: 0-35 points
        if "companies_house" in source or "opencorporates" in source:
            score += 35
        elif "company" in source.lower() or "corporate" in source.lower():
            score += 20
        
        # Institutional signals: 0-30 points
        if any(x in source for x in ["university", "institution", "academic", "educational"]):
            score += 30
        
        return min(100, score)
    
    def calculate_source_diversity_score(self, profile: dict[str, Any]) -> int:
        """
        Source diversity score: 0-100
        
        Based on:
          - Count of different sources
          - Count of categories
          - Cross-platform presence
        """
        raw_signals = profile.get("raw_signals", {})
        behavioral = profile.get("behavioral_intelligence", {})
        metadata = profile.get("metadata", {})
        
        score = 0
        
        # Raw signal sources: 0-40 points
        signal_sources = len([k for k in raw_signals.keys() if raw_signals[k]])
        if signal_sources > 0:
            score += min(40, signal_sources * 10)
        
        # Platform diversity: 0-35 points
        platforms = behavioral.get("platform_presence", [])
        if isinstance(platforms, list):
            unique_platforms = len(set([p for p in platforms if p]))
            if unique_platforms >= 1:
                score += min(35, 10 + unique_platforms * 8)
        
        # Categories inferred from sources: 0-25 points
        source_str = str(metadata.get("source", ""))
        categories = set()
        if any(x in source_str for x in ["github", "gitlab", "npm", "pypi"]):
            categories.add("tech")
        if any(x in source_str for x in ["govuk", "government", "spending"]):
            categories.add("government")
        if any(x in source_str for x in ["company", "corporate"]):
            categories.add("business")
        if any(x in source_str for x in ["gdelt", "news", "publication"]):
            categories.add("media")
        
        if categories:
            score += min(25, len(categories) * 8)
        
        return min(100, score)
    
    def calculate_entity_trust_score(self, profile: dict[str, Any]) -> int:
        """
        Entity trust score: 0-100
        
        Based on:
          - Verification signals
          - Evidence count
          - Confidence from resolution
          - Official sources
        """
        verification = profile.get("verification", {})
        identity = profile.get("identity_anchors", {})
        metadata = profile.get("metadata", {})
        
        score = 0
        
        # Core verification: 0-40 points
        if verification.get("is_real_entity"):
            score += 40
        
        # Verification confidence: 0-30 points
        verification_conf = float(verification.get("verification_confidence", 0))
        if verification_conf > 0.5:
            score += int(verification_conf * 30)
        
        # Evidence count: 0-20 points
        evidence_count = len(verification.get("public_profile_links", []))
        if evidence_count > 0:
            score += min(20, evidence_count * 7)
        
        # Resolution confidence: 0-10 points
        resolution_conf = float(identity.get("resolution_confidence", 0))
        if resolution_conf > 0.5:
            score += min(10, resolution_conf * 10)
        
        return min(100, score)
    
    def calculate_behavioral_pattern_score(self, profile: dict[str, Any]) -> int:
        """
        Behavioral pattern score: 0-100
        
        Based on:
          - Consistency across platforms
          - Activity patterns
          - Temporal patterns
        """
        behavioral = profile.get("behavioral_intelligence", {})
        identity = profile.get("identity_anchors", {})
        
        score = 0
        
        # Platform consistency: 0-40 points
        platforms = behavioral.get("platform_presence", [])
        if isinstance(platforms, list):
            unique_platforms = len(set([p for p in platforms if p]))
            if unique_platforms >= 2:
                score += min(40, unique_platforms * 12)
        
        # Tech stack consistency: 0-30 points
        tech_stack = behavioral.get("tech_stack", [])
        if isinstance(tech_stack, list):
            unique_techs = len(set([t for t in tech_stack if t]))
            if unique_techs >= 3:
                score += min(30, unique_techs * 6)
        
        # Activity pattern: 0-30 points
        peak_hours = behavioral.get("peak_activity_hours", [])
        if peak_hours and isinstance(peak_hours, list):
            score += min(30, len(peak_hours) * 6)
        
        return min(100, score)
    
    def calculate_activity_consistency_score(self, profile: dict[str, Any]) -> int:
        """
        Activity consistency score: 0-100
        
        Based on:
          - Temporal consistency
          - Regular activity patterns
          - Last signal recency
        """
        behavioral = profile.get("behavioral_intelligence", {})
        situational = profile.get("situational_intelligence", {})
        metadata = profile.get("metadata", {})
        
        score = 0
        
        # Base consistency: 0-50 points
        # Inferred from activity score
        activity = int(behavioral.get("digital_activity_score", 0))
        if activity > 50:
            score += 50
        elif activity > 30:
            score += 30
        elif activity > 0:
            score += 15
        
        # Recency: 0-30 points
        last_signal_str = situational.get("last_signal")
        if last_signal_str:
            try:
                last_signal = datetime.fromisoformat(last_signal_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                days_ago = (now - last_signal).days
                
                if days_ago <= 7:
                    score += 30
                elif days_ago <= 30:
                    score += 20
                elif days_ago <= 90:
                    score += 10
            except Exception:
                score += 5  # Default if can't parse
        
        # Collection date recency: 0-20 points
        collection_date_str = metadata.get("collection_date")
        if collection_date_str:
            try:
                collection_date = datetime.fromisoformat(collection_date_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                hours_ago = (now - collection_date).total_seconds() / 3600
                
                if hours_ago <= 24:
                    score += 20
                elif hours_ago <= 7 * 24:
                    score += 15
                elif hours_ago <= 30 * 24:
                    score += 10
            except Exception:
                pass
        
        return min(100, score)
    
    def calculate_signal_strength_score(self, profile: dict[str, Any]) -> int:
        """
        Overall signal strength score: 0-100
        
        Based on:
          - Count of raw signals
          - Depth of signal data
          - Quality of sources
          - Verification level
        """
        raw_signals = profile.get("raw_signals", {})
        verification = profile.get("verification", {})
        behavioral = profile.get("behavioral_intelligence", {})
        
        score = 0
        
        # Raw signal count: 0-35 points
        signal_count = len([v for v in raw_signals.values() if v])
        if signal_count > 0:
            score += min(35, signal_count * 8)
        
        # Signal data depth (not null): 0-30 points
        signal_depth = 0
        for signal_data in raw_signals.values():
            if isinstance(signal_data, dict):
                signal_depth += len([v for v in signal_data.values() if v])
        
        if signal_depth > 0:
            score += min(30, signal_depth // 2)
        
        # Verification level: 0-20 points
        if verification.get("is_real_entity"):
            score += 15
        
        if verification.get("public_profile_links"):
            score += 5
        
        # Behavioral data completeness: 0-15 points
        behavioral_fields = sum(1 for v in behavioral.values() if v)
        if behavioral_fields >= 3:
            score += 15
        elif behavioral_fields >= 2:
            score += 10
        elif behavioral_fields >= 1:
            score += 5
        
        return min(100, score)
    
    def _calculate_overall_confidence(
        self,
        social_activity: int,
        digital_pattern: int,
        spending_context: int,
        source_diversity: int,
        entity_trust: int,
        behavioral_pattern: int,
        activity_consistency: int,
        signal_strength: int,
    ) -> float:
        """
        Calculate overall confidence as weighted average.
        
        Returns: 0.0-1.0
        """
        # Weights
        weights = {
            "entity_trust": 0.25,           # Most important
            "source_diversity": 0.20,
            "signal_strength": 0.15,
            "social_activity": 0.12,
            "behavioral_pattern": 0.10,
            "digital_pattern": 0.10,
            "activity_consistency": 0.05,
            "spending_context": 0.03,
        }
        
        weighted_sum = (
            entity_trust * weights["entity_trust"] +
            source_diversity * weights["source_diversity"] +
            signal_strength * weights["signal_strength"] +
            social_activity * weights["social_activity"] +
            behavioral_pattern * weights["behavioral_pattern"] +
            digital_pattern * weights["digital_pattern"] +
            activity_consistency * weights["activity_consistency"] +
            spending_context * weights["spending_context"]
        )
        
        # Normalize to 0-1 range
        confidence = weighted_sum / 100.0
        return round(min(0.99, max(0.50, confidence)), 2)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# BATCH ENRICHMENT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def enrich_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich multiple profiles with all scores."""
    enricher = ProfileEnricher()
    return [enricher.enrich(profile) for profile in profiles]


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SINGLETON INSTANCE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_enricher: Optional[ProfileEnricher] = None


def get_enricher() -> ProfileEnricher:
    """Get or create the profile enricher."""
    global _enricher
    if _enricher is None:
        _enricher = ProfileEnricher()
    return _enricher


def enrich_one(profile: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to enrich a single profile."""
    return get_enricher().enrich(profile)

