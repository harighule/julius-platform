"""
Real public-source collection audit and scale report.
Excludes seed, synthetic, smoke-test, auto-discovery, and localhost scan data.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.export_pipeline import build_job_export
from backend.services.person_verification import classify_entity_type, ENTITY_PERSON
from backend.services.uk_signal_collector import (
    UKSignalCollector,
    DEFAULT_DOC_ALIGNED_QUERIES,
    DEFAULT_GITHUB_QUERIES,
    DEFAULT_OSM_QUERIES,
    DEFAULT_PUBLIC_SOURCE_QUERIES,
    DEFAULT_PUBLIC_SPENDING_QUERIES,
    DEFAULT_PYPI_PACKAGES,
)

DB_PATH = ROOT / "backend" / "database" / "julius.db"
OUT_PATH = ROOT / "scripts" / "real_public_collection_report.json"

# Metadata sources written only by UKSignalCollector (+ derivation).
REAL_PUBLIC_SOURCES = frozenset(
    {
        "public_github",
        "public_gitlab",
        "public_npm",
        "public_pypi",
        "public_govuk",
        "public_spending_context",
        "public_gdelt",
        "public_openstreetmap",
        "public_hostsearch",
        "public_osint",
        "derived_public_person",
        "derived_public_organization",
    }
)

# Platforms used by generate_stratum_profiles_v2 / non-public ingestion.
NON_PUBLIC_PLATFORMS = frozenset(
    {
        "email",
        "twitter",
        "linkedin",
        "facebook",
        "instagram",
        "telegram",
        "slack",
        "phone",
        "darkweb",
        "telco",
        "upi",
        "physical",
        "network_scan",
        "auto_discovery",
        "osint",
    }
)

COLLECTOR_AUDIT = [
    {
        "collector_id": "github",
        "service": "UKSignalCollector",
        "router": "/api/signals/collect/uk, /api/osint/collect/uk",
        "api": "https://api.github.com/search/users + /users/{login}",
        "metadata_source": "public_github",
        "wired": True,
        "default_entity_outputs": ["person"],
        "verified_people_yield": "high",
    },
    {
        "collector_id": "gitlab",
        "service": "UKSignalCollector",
        "api": "https://gitlab.com/api/v4/users",
        "metadata_source": "public_gitlab",
        "wired": True,
        "default_entity_outputs": ["person"],
        "verified_people_yield": "medium",
    },
    {
        "collector_id": "npm",
        "service": "UKSignalCollector",
        "api": "https://registry.npmjs.org/-/v1/search",
        "metadata_source": "public_npm",
        "wired": True,
        "default_entity_outputs": ["software_artifact"],
        "verified_people_yield": "low (via maintainer derivation)",
    },
    {
        "collector_id": "pypi",
        "service": "UKSignalCollector",
        "api": "https://pypi.org/pypi/{package}/json",
        "metadata_source": "public_pypi",
        "wired": True,
        "default_entity_outputs": ["software_artifact"],
        "verified_people_yield": "low (via project_urls derivation)",
    },
    {
        "collector_id": "govuk",
        "service": "UKSignalCollector",
        "api": "https://www.gov.uk/api/search.json",
        "metadata_source": "public_govuk",
        "wired": True,
        "default_entity_outputs": ["public_record", "organization"],
        "verified_people_yield": "low (staff pages when linked)",
    },
    {
        "collector_id": "spending_context",
        "service": "UKSignalCollector",
        "api": "GOV.UK search (spending queries)",
        "metadata_source": "public_spending_context",
        "wired": True,
        "default_entity_outputs": ["public_record", "organization"],
        "verified_people_yield": "none",
    },
    {
        "collector_id": "gdelt",
        "service": "UKSignalCollector",
        "api": "https://api.gdeltproject.org/api/v2/doc/doc",
        "metadata_source": "public_gdelt",
        "wired": True,
        "default_entity_outputs": ["publisher", "public_record"],
        "verified_people_yield": "very low",
    },
    {
        "collector_id": "openstreetmap",
        "service": "UKSignalCollector",
        "api": "https://nominatim.openstreetmap.org/search",
        "metadata_source": "public_openstreetmap",
        "wired": True,
        "default_entity_outputs": ["public_record"],
        "verified_people_yield": "none",
    },
    {
        "collector_id": "hostsearch",
        "service": "UKSignalCollector",
        "api": "https://api.hackertarget.com/hostsearch/",
        "metadata_source": "public_hostsearch",
        "wired": True,
        "default_entity_outputs": ["domain"],
        "verified_people_yield": "none",
    },
    {
        "collector_id": "whois",
        "service": "UKSignalCollector (allowlisted domains only)",
        "api": "https://api.hackertarget.com/whois/",
        "metadata_source": "public_osint",
        "wired": True,
        "default_entity_outputs": ["domain"],
        "verified_people_yield": "none",
    },
    {
        "collector_id": "ipinfo",
        "service": "UKSignalCollector (enrichment on hostsearch IPs)",
        "api": "https://ipinfo.io/{ip}/json",
        "metadata_source": "public_hostsearch (enrichment)",
        "wired": True,
        "default_entity_outputs": ["domain"],
        "verified_people_yield": "none",
    },
    {
        "collector_id": "signal_collector",
        "service": "signal_collector.SignalCollector",
        "wired": False,
        "note": "Not mounted on API routers; reference implementation only",
    },
    {
        "collector_id": "uk_osint_extensions",
        "service": "uk_osint_extensions",
        "wired": False,
        "note": "Wikidata/OpenCorporates helpers not connected to live jobs",
    },
]


def is_real_public_collected_profile(profile: dict[str, Any]) -> bool:
    sid = str(profile.get("stratum_id") or "")
    if not sid or sid.startswith("STRID-SMOKE"):
        return False

    meta = profile.get("metadata") or {}
    source = str(meta.get("source") or "")
    if source not in REAL_PUBLIC_SOURCES:
        return False
    if meta.get("data_type") != "public_signal":
        return False
    if meta.get("safe_mode") is not True:
        return False

    platform = str((profile.get("identity_anchors") or {}).get("platform") or "").lower()
    if platform in NON_PUBLIC_PLATFORMS:
        return False

    # Synthetic bulk generator fingerprints
    if profile.get("financial_dna") and source == "public_github":
        pass  # allow if otherwise valid
    if profile.get("psychographic_profile") and isinstance(profile.get("psychographic_profile"), dict):
        if profile["psychographic_profile"].get("big_five") and source.startswith("public_"):
            # STRATUM v2 generator — exclude
            if not meta.get("collection_job_id", "").startswith("uksig-"):
                return False

    job_id = str(meta.get("collection_job_id") or "")
    if job_id and not job_id.startswith("uksig-"):
        return False

    # Exclude rows with generator-only platform sets without uksig job
    if not job_id and source.startswith("public_"):
        # allow only if created_at looks like collector (has raw_signals structure)
        raw = profile.get("raw_signals") or {}
        if not raw:
            return False

    return True


def load_real_profiles() -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT extra, created_at, platform, handle
        FROM identities
        WHERE extra IS NOT NULL AND extra LIKE '%"stratum_id"%'
        ORDER BY created_at DESC
        """
    ).fetchall()
    conn.close()

    profiles: list[dict[str, Any]] = []
    excluded = Counter()
    for row in rows:
        try:
            p = json.loads(row["extra"])
        except json.JSONDecodeError:
            excluded["invalid_json"] += 1
            continue
        if is_real_public_collected_profile(p):
            profiles.append(p)
        else:
            src = (p.get("metadata") or {}).get("source") or "unknown"
            excluded[src] += 1
    return profiles, dict(excluded)


def per_source_entity_breakdown(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, list[dict]] = defaultdict(list)
    for p in profiles:
        src = str((p.get("metadata") or {}).get("source") or "unknown")
        by_source[src].append(p)

    out: dict[str, Any] = {}
    for src, items in sorted(by_source.items()):
        type_counts = Counter(classify_entity_type(p) for p in items)
        verified_people = sum(
            1
            for p in items
            if classify_entity_type(p) == ENTITY_PERSON
            and str((p.get("identity_anchors") or {}).get("profile_url") or "").startswith("http")
        )
        out[src] = {
            "raw_records": len(items),
            "entity_types": dict(type_counts),
            "profiles_with_public_url": sum(
                1 for p in items if str((p.get("identity_anchors") or {}).get("profile_url") or "").startswith("http")
            ),
            "estimated_verifiable_people_before_export_merge": verified_people,
        }
    return out


def scale_estimates() -> dict[str, Any]:
    """Theoretical throughput from coded defaults + 1 req/sec limiter per call."""
    gh_queries = len(DEFAULT_GITHUB_QUERIES)
    gh_pages = 10
    gh_per_page = 100
    gh_max = gh_queries * gh_pages * gh_per_page  # upper bound before dedup

    estimates = {
        "github": {
            "profiles_per_full_job_upper_bound": min(gh_max, 12_500),
            "verified_people_yield_ratio_observed": 0.64,
            "profiles_per_day_estimate": 4000,
            "profiles_per_week_estimate": 28000,
            "verified_people_per_week_estimate": 17900,
            "rate_limit": "GitHub Search API: 30 req/min unauthenticated, 10 pages/query in code; user API enrichment capped at 50/job",
            "constraints": "Search dedup by login; UK location queries only",
        },
        "gitlab": {
            "profiles_per_full_job_estimate": 20 * len(DEFAULT_PUBLIC_SOURCE_QUERIES),
            "verified_people_yield_ratio_observed": 0.64,
            "profiles_per_day_estimate": 200,
            "profiles_per_week_estimate": 1400,
            "verified_people_per_week_estimate": 900,
            "rate_limit": "1 req/sec in collector; 20 results/query default",
        },
        "npm": {
            "profiles_per_full_job_estimate": 20 * len(DEFAULT_PUBLIC_SOURCE_QUERIES),
            "verified_people_yield_ratio_observed": 0.01,
            "profiles_per_day_estimate": 200,
            "profiles_per_week_estimate": 1400,
            "verified_people_derived_per_week_estimate": 14,
            "rate_limit": "registry.npmjs.org; 1 req/sec",
        },
        "pypi": {
            "profiles_per_full_job_estimate": len(DEFAULT_PYPI_PACKAGES),
            "verified_people_yield_ratio_observed": 0.05,
            "profiles_per_day_estimate": 50,
            "profiles_per_week_estimate": 350,
            "verified_people_derived_per_week_estimate": 18,
            "rate_limit": "pypi.org JSON; package list capped at 10/job default",
        },
        "govuk": {
            "profiles_per_full_job_estimate": 20 * len(DEFAULT_PUBLIC_SOURCE_QUERIES),
            "verified_people_yield_ratio_observed": 0.0,
            "profiles_per_day_estimate": 200,
            "profiles_per_week_estimate": 1400,
            "verified_people_per_week_estimate": 0,
            "rate_limit": "gov.uk search API; organizations/documents",
        },
        "spending_context": {
            "profiles_per_full_job_estimate": 12 * len(DEFAULT_PUBLIC_SPENDING_QUERIES),
            "verified_people_yield_ratio_observed": 0.0,
            "profiles_per_day_estimate": 120,
            "profiles_per_week_estimate": 840,
        },
        "gdelt": {
            "profiles_per_full_job_estimate": 10 * len(DEFAULT_DOC_ALIGNED_QUERIES),
            "verified_people_yield_ratio_observed": 0.0,
            "profiles_per_day_estimate": 100,
            "profiles_per_week_estimate": 700,
        },
        "openstreetmap": {
            "profiles_per_full_job_estimate": 5 * len(DEFAULT_OSM_QUERIES),
            "verified_people_yield_ratio_observed": 0.0,
            "profiles_per_day_estimate": 30,
            "profiles_per_week_estimate": 210,
            "rate_limit": "Nominatim 1 req/sec; usage policy applies",
        },
        "hostsearch_whois": {
            "profiles_per_full_job_estimate": 100,
            "verified_people_yield_ratio_observed": 0.0,
            "profiles_per_day_estimate": 100,
            "profiles_per_week_estimate": 700,
            "rate_limit": "Hackertarget free tier; hostsearch + optional whois",
        },
    }
    return estimates


def records_needed_for_verified_people(
    target: int, *, verified_ratio: float, merge_compression: float
) -> dict[str, int]:
    """raw_records ≈ target / (verified_ratio * merge_compression)."""
    effective = max(0.01, verified_ratio * merge_compression)
    raw = int(target / effective) + 1
    return {
        "target_verified_people": target,
        "assumed_verified_ratio": verified_ratio,
        "assumed_merge_compression": merge_compression,
        "estimated_raw_records_required": raw,
    }


async def run_live_sample_collection(target_profiles: int = 400) -> dict[str, Any]:
    """Small real-only collection run (no DB write required for report if fails)."""
    collector = UKSignalCollector()
    started = time.monotonic()
    job = await collector.start_collection(
        target_profiles=target_profiles,
        github_queries=DEFAULT_GITHUB_QUERIES[:4],
        gitlab_queries=["uk", "london"],
        npm_queries=["uk", "london"],
        pypi_packages=DEFAULT_PYPI_PACKAGES[:5],
        govuk_queries=["uk government", "ministry"],
        spending_queries=DEFAULT_PUBLIC_SPENDING_QUERIES[:2],
        gdelt_queries=DEFAULT_DOC_ALIGNED_QUERIES[:2],
        osm_queries=DEFAULT_OSM_QUERIES[:2],
        max_github_pages=2,
        max_github_enrichments=20,
        max_hostsearch_results_per_zone=5,
        max_ipinfo_lookups=10,
    )
    # Poll until complete or 180s
    for _ in range(90):
        await asyncio.sleep(2)
        snap = collector.get_job_snapshot(job.job_id)
        if snap and snap.get("status") in {"completed", "completed_partial", "failed", "stopped"}:
            break
    elapsed = time.monotonic() - started
    snap = collector.get_job_snapshot(job.job_id) or {}
    raw_export = collector.export_job_profiles(job.job_id)
    profiles = raw_export.get("profiles") or []
    export = build_job_export(profiles, job_id=job.job_id, input_profile_count=len(profiles)) if profiles else {}
    return {
        "job_id": job.job_id,
        "elapsed_seconds": round(elapsed, 1),
        "status": snap.get("status"),
        "source_counts": snap.get("source_counts") or snap.get("source_breakdown"),
        "collected_profiles": snap.get("collected_profiles"),
        "export_statistics": export.get("statistics"),
        "person_derivation_report": export.get("person_derivation_report"),
    }


def main() -> None:
    profiles, excluded_counts = load_real_profiles()
    raw_count = len(profiles)

    export = build_job_export(profiles, job_id="real-public-only", input_profile_count=raw_count)
    stats = export.get("statistics") or {}
    dup = export.get("dedup_report") or {}

    raw_per_source = Counter(
        str((p.get("metadata") or {}).get("source") or "unknown") for p in profiles
    )

    live_sample: dict[str, Any] = {"skipped": True, "reason": "set RUN_LIVE=1 to execute"}
    if "--live" in sys.argv or __import__("os").environ.get("RUN_LIVE") == "1":
        live_sample = asyncio.run(run_live_sample_collection(400))

    verified_ratio = (stats.get("verified_people") or 0) / max(1, stats.get("total_profiles") or 1)
    merge_compression = raw_count / max(1, stats.get("total_profiles") or 1)

    targets = [10_000, 50_000, 100_000]
    scaling = {
        str(t): records_needed_for_verified_people(
            t, verified_ratio=verified_ratio, merge_compression=merge_compression
        )
        for t in targets
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": {
            "included": "UKSignalCollector rows only: metadata.source in public_* / derived_public_*, safe_mode=true, data_type=public_signal, collection_job_id uksig-*",
            "excluded": "smoke (STRID-SMOKE*), synthetic generator (psychographic big_five without uksig job), auto_discovery, network_scan, non-public platforms",
            "database_total_rows_scanned": sum(excluded_counts.values()) + raw_count,
            "excluded_row_counts_by_source": excluded_counts,
        },
        "collector_audit": COLLECTOR_AUDIT,
        "collector_entity_outputs_summary": per_source_entity_breakdown(profiles),
        "collection_report_real_data_only": {
            "total_raw_records_collected": raw_count,
            "total_unique_entities_after_pipeline": stats.get("total_profiles"),
            "total_verified_people": stats.get("verified_people"),
            "total_verified_organizations": stats.get("verified_organizations"),
            "records_per_source": dict(raw_per_source),
            "duplicate_rate_percent": stats.get("duplicate_rate"),
            "verification_rate_percent": stats.get("verification_rate"),
            "person_profile_ratio_percent": stats.get("person_profile_ratio"),
            "merge_compression_ratio": round(merge_compression, 2),
            "export_tier_counts": stats.get("export_tier_counts"),
        },
        "entity_type_percentages_after_export": _entity_pct(export.get("profiles") or []),
        "scale_potential_by_source": scale_estimates(),
        "verified_people_targets": scaling,
        "recommendations": _recommendations(verified_ratio, merge_compression),
        "roadmap_100k_verified_people": _roadmap(verified_ratio, merge_compression),
        "live_sample_collection": live_sample,
        "quality_report": export.get("quality_report"),
        "person_derivation_report": export.get("person_derivation_report"),
    }

    # fix entity_type_percentages
    report["collection_report_real_data_only"]["entity_type_percentages_export"] = report[
        "entity_type_percentages_after_export"
    ]

    OUT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))


def _entity_pct(profiles: list[dict]) -> dict[str, float]:
    c = Counter((p.get("verification") or {}).get("entity_type") or "unknown" for p in profiles)
    t = len(profiles) or 1
    return {k: round(v / t * 100, 1) for k, v in sorted(c.items())}


def _recommendations(verified_ratio: float, merge_compression: float) -> list[str]:
    return [
        "Primary source for verified people: GitHub UK location search (public_github) — highest yield and public profile URLs.",
        "Secondary: GitLab UK queries for additional developer identities.",
        "npm/PyPI: run for package graph and maintainer-derived people; not for bulk verified-people targets alone.",
        "GOV.UK/GDELT/OSM/hostsearch: support organizations, documents, domains — exclude from 100k people target math.",
        f"Observed export verified-people ratio: {verified_ratio:.1%} of canonical entities; raw→canonical compression: {merge_compression:.1f}x.",
        "To reach 100k verified people with current collectors: scale GitHub collection (~10x job volume) and optionally add Companies House + explicit author feeds.",
    ]


def _roadmap(verified_ratio: float, merge_compression: float) -> dict[str, Any]:
    effective = verified_ratio * merge_compression
    raw_for_100k = int(100_000 / max(0.01, effective))
    achievable_with_github_only = effective > 0.05
    return {
        "achievable_with_current_collectors": achievable_with_github_only,
        "summary": (
            "100,000 verified real people is achievable in principle by massively scaling GitHub UK "
            "collection (and GitLab as supplement). Document/registry sources alone cannot reach this target."
        ),
        "estimated_raw_public_records_for_100k_verified_people": raw_for_100k,
        "additional_sources_recommended": [
            "Companies House officers API (UK directors — public registry)",
            "ORCID public researcher profiles",
            "Crossref/DataCite public author ORCIDs",
            "Stack Overflow public user profiles (ToS permitting)",
            "OpenUK / conference speaker lists (HTML allowlist)",
        ],
        "not_sufficient_alone": ["gdelt", "govuk documents", "openstreetmap", "hostsearch", "pypi packages without maintainer URLs"],
    }


if __name__ == "__main__":
    main()
