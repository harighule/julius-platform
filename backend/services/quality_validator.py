"""
STRATUM Quality Validator Service

Ensures profiles meet production standards:
  - Schema validation (required fields, types)
  - Score validation (0-100 ranges, NaN checks)
  - Verification compliance (real entity evidence)
  - Provenance completeness (all sources tracked)
  - Null density checks (minimum data quality)
  - Duplication detection
  - No synthetic data validation
  - Export quality reports

All validation is deterministic and local-only.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# VALIDATION RESULTS
# ─────────────────────────────────────────────────────────────────────────

class ValidationSeverity(str, Enum):
    ERROR = "error"      # Profile fails validation
    WARNING = "warning"  # Profile passes but has issues
    INFO = "info"        # Informational
    PASS = "pass"        # Validation passed


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: ValidationSeverity
    category: str  # "schema", "verification", "scores", "provenance", etc.
    field: str
    message: str
    suggested_fix: Optional[str] = None


@dataclass
class ValidationReport:
    """Complete validation report for a profile."""
    stratum_id: str
    is_valid: bool
    score: float  # 0-100
    issues: list[ValidationIssue] = field(default_factory=list)
    
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)
    
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)
    
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.INFO)


@dataclass
class BatchValidationReport:
    """Validation report for a batch of profiles."""
    profiles_checked: int
    valid_profiles: int
    invalid_profiles: int
    validation_rate: float  # 0-100
    
    total_errors: int = 0
    total_warnings: int = 0
    total_infos: int = 0
    
    duplicate_count: int = 0
    synthetic_detected: int = 0
    low_quality_count: int = 0
    
    profile_reports: list[ValidationReport] = field(default_factory=list)
    
    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"Validated {self.profiles_checked} profiles: "
            f"{self.valid_profiles} valid, {self.invalid_profiles} invalid "
            f"(rate: {self.validation_rate:.1f}%) | "
            f"Errors: {self.total_errors}, Warnings: {self.total_warnings}"
        )


# ─────────────────────────────────────────────────────────────────────────
# QUALITY VALIDATOR
# ─────────────────────────────────────────────────────────────────────────

class QualityValidator:
    """Validates profiles for production quality."""
    
    # Required top-level fields
    REQUIRED_FIELDS = {
        "stratum_id",
        "identity_anchors",
        "behavioral_intelligence",
        "situational_intelligence",
        "metadata",
        "verification",
    }
    
    # Required in identity_anchors
    REQUIRED_IDENTITY_FIELDS = {"platform"}  # handle optional
    
    # Required in metadata
    REQUIRED_METADATA_FIELDS = {"source", "collection_date", "country", "data_type"}
    
    # Required in verification
    REQUIRED_VERIFICATION_FIELDS = {"is_real_entity", "entity_type", "verification_confidence"}
    
    # Valid entity types
    VALID_ENTITY_TYPES = {
        "person",
        "organization",
        "publisher",
        "public_record",
        "software_artifact",
        "domain",
        "institution",
        "digital_identity",
        "unknown",
    }
    
    # Score fields that should be 0-100
    SCORE_FIELDS = {
        "public_social_activity_score",
        "public_digital_pattern_score",
        "public_spending_context_score",
        "source_diversity_score",
        "entity_trust_score",
        "behavioral_pattern_score",
        "activity_consistency_score",
        "signal_strength_score",
    }
    
    def __init__(self):
        pass
    
    def validate(self, profile: dict[str, Any]) -> ValidationReport:
        """Validate a single profile."""
        stratum_id = str(profile.get("stratum_id", "UNKNOWN"))
        issues: list[ValidationIssue] = []
        
        # Schema validation
        issues.extend(self._validate_schema(profile))
        
        # Verification validation
        issues.extend(self._validate_verification(profile))
        
        # Score validation
        issues.extend(self._validate_scores(profile))
        
        # Provenance validation
        issues.extend(self._validate_provenance(profile))
        
        # Data quality checks
        issues.extend(self._validate_data_quality(profile))
        
        # Synthetic data detection
        issues.extend(self._detect_synthetic_data(profile))
        
        # Calculate validity
        error_issues = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        is_valid = len(error_issues) == 0
        
        # Calculate score
        score = self._calculate_validation_score(profile, issues)
        
        return ValidationReport(
            stratum_id=stratum_id,
            is_valid=is_valid,
            score=score,
            issues=issues,
        )
    
    def validate_batch(self, profiles: list[dict[str, Any]]) -> BatchValidationReport:
        """Validate a batch of profiles."""
        reports = []
        duplicates = {}
        
        for profile in profiles:
            report = self.validate(profile)
            reports.append(report)
        
        # Detect duplicates across batch
        canonical_keys = {}
        for profile in profiles:
            key = self._get_canonical_key(profile)
            if key in canonical_keys:
                duplicates[profile.get("stratum_id", "")] = canonical_keys[key]
            else:
                canonical_keys[key] = profile.get("stratum_id", "")
        
        # Aggregate
        valid_count = sum(1 for r in reports if r.is_valid)
        invalid_count = len(reports) - valid_count
        validation_rate = (valid_count / len(reports) * 100) if reports else 0
        
        synthetic_count = sum(
            1 for r in reports
            if any(i.severity == ValidationSeverity.ERROR and "synthetic" in i.message.lower() for i in r.issues)
        )
        
        low_quality_count = sum(
            1 for r in reports
            if r.score < 50
        )
        
        total_errors = sum(r.error_count() for r in reports)
        total_warnings = sum(r.warning_count() for r in reports)
        total_infos = sum(r.info_count() for r in reports)
        
        return BatchValidationReport(
            profiles_checked=len(profiles),
            valid_profiles=valid_count,
            invalid_profiles=invalid_count,
            validation_rate=validation_rate,
            total_errors=total_errors,
            total_warnings=total_warnings,
            total_infos=total_infos,
            duplicate_count=len(duplicates),
            synthetic_detected=synthetic_count,
            low_quality_count=low_quality_count,
            profile_reports=reports,
        )
    
    # Validation methods
    
    def _validate_schema(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Validate required schema."""
        issues = []
        
        # Check top-level fields
        for field in self.REQUIRED_FIELDS:
            if field not in profile:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="schema",
                    field=field,
                    message=f"Missing required field: {field}",
                    suggested_fix=f"Ensure {field} exists in profile",
                ))
        
        # Validate identity_anchors
        identity = profile.get("identity_anchors", {})
        for field in self.REQUIRED_IDENTITY_FIELDS:
            if field not in identity:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="schema",
                    field=f"identity_anchors.{field}",
                    message=f"Missing field in identity_anchors: {field}",
                ))
        
        # Validate metadata
        metadata = profile.get("metadata", {})
        for field in self.REQUIRED_METADATA_FIELDS:
            if field not in metadata:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="schema",
                    field=f"metadata.{field}",
                    message=f"Missing field in metadata: {field}",
                ))
        
        # Validate verification
        verification = profile.get("verification", {})
        for field in self.REQUIRED_VERIFICATION_FIELDS:
            if field not in verification:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="schema",
                    field=f"verification.{field}",
                    message=f"Missing required field in verification: {field}",
                    suggested_fix="Ensure all verification fields are present",
                ))
        
        return issues
    
    def _validate_verification(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Validate verification requirements."""
        issues = []
        verification = profile.get("verification", {})
        
        # Check is_real_entity
        is_real = verification.get("is_real_entity")
        if is_real is not True:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="verification",
                field="verification.is_real_entity",
                message="Profile must have is_real_entity=true (no synthetic profiles)",
                suggested_fix="Only collect real entities from public sources",
            ))
        
        # Check entity_type
        entity_type = verification.get("entity_type")
        if entity_type not in self.VALID_ENTITY_TYPES:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="verification",
                field="verification.entity_type",
                message=f"Invalid entity_type: {entity_type}. Must be one of: {', '.join(self.VALID_ENTITY_TYPES)}",
                suggested_fix=f"Set entity_type to a valid value",
            ))
        
        # Check verification_confidence
        conf = verification.get("verification_confidence", 0)
        try:
            conf_float = float(conf)
            if conf_float < 0.5:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="verification",
                    field="verification.verification_confidence",
                    message=f"Low verification confidence: {conf_float}",
                    suggested_fix="Ensure strong evidence backing this profile",
                ))
        except (TypeError, ValueError):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="verification",
                field="verification.verification_confidence",
                message="verification_confidence must be a number",
            ))
        
        if verification.get("is_real_person") is True:
            evidence = verification.get("public_identity_evidence") or profile.get("public_identity_evidence") or []
            if not evidence:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="verification",
                    field="verification.public_identity_evidence",
                    message="Verified person should include structured public_identity_evidence",
                    suggested_fix="Derive person profiles only from public URLs present in source payloads",
                ))
            entity_type = verification.get("entity_type")
            if entity_type == "person":
                package_only = all(
                    "npmjs.com" in str(item.get("url") or "")
                    and "github.com" not in str(item.get("url") or "")
                    and "gitlab.com" not in str(item.get("url") or "")
                    for item in evidence
                    if isinstance(item, dict)
                )
                if evidence and package_only and not verification.get("public_profile_links"):
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category="verification",
                        field="verification.public_identity_evidence",
                        message="Person verification should include a developer profile URL when available",
                        suggested_fix="Link npm/pypi maintainers to GitHub/GitLab URLs from project_urls when present",
                    ))

        # Check public_profile_links (if claiming real entity)
        if is_real is True:
            links = verification.get("public_profile_links", [])
            if not links:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="verification",
                    field="verification.public_profile_links",
                    message="Real entity should have public_profile_links evidence",
                    suggested_fix="Include URLs to public profiles/sources",
                ))
            else:
                # Validate links are actual URLs
                for link in links:
                    if not isinstance(link, str) or not link.startswith(("http://", "https://")):
                        issues.append(ValidationIssue(
                            severity=ValidationSeverity.ERROR,
                            category="verification",
                            field="verification.public_profile_links",
                            message=f"Invalid URL in public_profile_links: {link}",
                            suggested_fix="Ensure all links are valid HTTP(S) URLs",
                        ))
        
        return issues
    
    def _validate_scores(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Validate derived scores."""
        issues = []
        derived_signals = profile.get("derived_signals", {})
        
        for score_field in self.SCORE_FIELDS:
            if score_field not in derived_signals:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    category="scores",
                    field=f"derived_signals.{score_field}",
                    message=f"Missing score field: {score_field}",
                    suggested_fix="Run profile enricher to calculate scores",
                ))
                continue
            
            score = derived_signals[score_field]
            try:
                score_int = int(score)
                if score_int < 0 or score_int > 100:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category="scores",
                        field=f"derived_signals.{score_field}",
                        message=f"Score out of range (0-100): {score_int}",
                        suggested_fix="Ensure all scores are in 0-100 range",
                    ))
            except (TypeError, ValueError):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="scores",
                    field=f"derived_signals.{score_field}",
                    message=f"Score must be numeric, got: {type(score).__name__}",
                ))
        
        # Check overall_confidence
        overall_conf = derived_signals.get("overall_confidence")
        if overall_conf is not None:
            try:
                conf_float = float(overall_conf)
                if conf_float < 0 or conf_float > 1.0:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category="scores",
                        field="derived_signals.overall_confidence",
                        message=f"Overall confidence out of range (0-1): {conf_float}",
                    ))
            except (TypeError, ValueError):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="scores",
                    field="derived_signals.overall_confidence",
                    message=f"overall_confidence must be numeric",
                ))
        
        return issues
    
    def _validate_provenance(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Validate provenance tracking."""
        issues = []
        
        # Check collection_date exists and is valid
        metadata = profile.get("metadata", {})
        collection_date = metadata.get("collection_date")
        
        if not collection_date:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="provenance",
                field="metadata.collection_date",
                message="Missing collection_date in metadata",
                suggested_fix="Include when profile was collected",
            ))
        else:
            # Try to parse as ISO datetime
            try:
                datetime.fromisoformat(collection_date.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="provenance",
                    field="metadata.collection_date",
                    message="collection_date should be ISO 8601 format",
                    suggested_fix="Use datetime.now(timezone.utc).isoformat()",
                ))
        
        # Check source is specified
        source = metadata.get("source")
        if not source:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="provenance",
                field="metadata.source",
                message="Missing source in metadata",
                suggested_fix="Specify where this profile was collected from",
            ))
        
        # Check raw_signals has entries
        raw_signals = profile.get("raw_signals", {})
        if not raw_signals:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="provenance",
                field="raw_signals",
                message="No raw signals recorded",
                suggested_fix="Include original source data for auditability",
            ))
        
        return issues
    
    def _validate_data_quality(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Validate data quality and density."""
        issues = []
        
        # Calculate null density
        def count_fields(obj: Any, max_depth: int = 2) -> tuple[int, int]:
            """Count total fields and non-null fields."""
            total = 0
            non_null = 0
            
            if not isinstance(obj, dict):
                return 0, 0
            
            if max_depth <= 0:
                return 0, 0
            
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    sub_total, sub_non_null = count_fields(v, max_depth - 1)
                    total += sub_total
                    non_null += sub_non_null
                else:
                    total += 1
                    if v not in (None, "", [], {}):
                        non_null += 1
            
            return total, non_null
        
        total_fields, non_null_fields = count_fields(profile, max_depth=2)
        
        if total_fields > 0:
            null_density = 1 - (non_null_fields / total_fields)
            if null_density > 0.7:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="data_quality",
                    field="",
                    message=f"High null density: {null_density:.1%} fields are empty",
                    suggested_fix="Ensure profile has sufficient data from sources",
                ))
        
        # Check identity_anchors has at least one identifier
        identity = profile.get("identity_anchors", {})
        identifiers = ["handle", "email", "domain", "profile_url", "display_name"]
        id_count = sum(1 for id_field in identifiers if identity.get(id_field))
        
        if id_count == 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="data_quality",
                field="identity_anchors",
                message="No identifiers in identity_anchors",
                suggested_fix="Must have at least one of: handle, email, domain, profile_url, display_name",
            ))
        
        return issues
    
    def _detect_synthetic_data(self, profile: dict[str, Any]) -> list[ValidationIssue]:
        """Detect signs of synthetic/fabricated data."""
        issues = []
        
        # Check for obviously synthetic patterns
        identity = profile.get("identity_anchors", {})
        behavioral = profile.get("behavioral_intelligence", {})
        
        # Pattern: Perfect round numbers suggest fabrication
        for key in ["followers", "public_repos", "contribution_score"]:
            value = behavioral.get(key, 0)
            if isinstance(value, (int, float)) and value > 0:
                # Perfect thousands/ten-thousands
                if value % 1000 == 0 and value > 100000:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category="synthetic_detection",
                        field=f"behavioral_intelligence.{key}",
                        message=f"Suspiciously round number: {value}",
                        suggested_fix="Verify against actual API response",
                    ))
        
        # Pattern: All scores exactly equal (unlikely)
        derived = profile.get("derived_signals", {})
        scores = [v for k, v in derived.items() if k in self.SCORE_FIELDS and isinstance(v, (int, float))]
        if len(scores) > 2 and len(set(scores)) == 1 and scores[0] not in (0, 50, 100):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="synthetic_detection",
                field="derived_signals",
                message="All scores are identical (suspicious)",
                suggested_fix="Verify enricher is calculating correctly",
            ))
        
        # Pattern: No actual public profile links but claiming real
        verification = profile.get("verification", {})
        if verification.get("is_real_entity") is True:
            links = verification.get("public_profile_links", [])
            if not links:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="synthetic_detection",
                    field="verification",
                    message="Claims real entity but has no public profile links",
                    suggested_fix="Include actual URLs where entity can be verified",
                ))
        
        return issues
    
    # Helper methods
    
    def _get_canonical_key(self, profile: dict[str, Any]) -> str:
        """Get a canonical key for duplicate detection."""
        identity = profile.get("identity_anchors", {})
        metadata = profile.get("metadata", {})
        
        # Build key from platform + handle/email
        platform = identity.get("platform", "")
        handle = identity.get("handle", "")
        email = identity.get("email", "")
        
        if platform and handle:
            return f"{platform}:{handle}".lower()
        elif email:
            return f"email:{email}".lower()
        elif platform:
            name = identity.get("display_name", "")
            if name:
                return f"{platform}:{name}".lower()
        
        # Fallback to stratum_id
        return profile.get("stratum_id", "unknown")
    
    def _calculate_validation_score(
        self,
        profile: dict[str, Any],
        issues: list[ValidationIssue],
    ) -> float:
        """Calculate a validation quality score."""
        score = 100.0
        
        # Deduct for errors
        error_count = sum(1 for i in issues if i.severity == ValidationSeverity.ERROR)
        score -= error_count * 25
        
        # Deduct for warnings
        warning_count = sum(1 for i in issues if i.severity == ValidationSeverity.WARNING)
        score -= warning_count * 5
        
        # Bonus for complete profiles
        verification = profile.get("verification", {})
        if verification.get("is_real_entity") is True and verification.get("public_profile_links"):
            score += 10
        
        raw_signals = profile.get("raw_signals", {})
        if len(raw_signals) >= 2:
            score += 5
        
        derived = profile.get("derived_signals", {})
        if len([v for k, v in derived.items() if k in self.SCORE_FIELDS]) >= 4:
            score += 5
        
        return max(0, min(100, score))


# ─────────────────────────────────────────────────────────────────────────
# SINGLETON INSTANCE
# ─────────────────────────────────────────────────────────────────────────

_validator: Optional[QualityValidator] = None


def get_validator() -> QualityValidator:
    """Get or create the quality validator."""
    global _validator
    if _validator is None:
        _validator = QualityValidator()
    return _validator


def validate_profile(profile: dict[str, Any]) -> ValidationReport:
    """Convenience function to validate a profile."""
    return get_validator().validate(profile)


def validate_batch(profiles: list[dict[str, Any]]) -> BatchValidationReport:
    """Convenience function to validate a batch."""
    return get_validator().validate_batch(profiles)
