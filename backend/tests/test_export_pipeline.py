"""Tests for shared export pipeline."""

from backend.services.export_pipeline import build_job_export
from backend.services.person_verification import (
    build_export_statistics,
    prioritize_export_profiles,
    verify_profile,
)


def _github_profile() -> dict:
    return {
        "stratum_id": "STRID-PIPE01",
        "identity_anchors": {
            "handle": "octocat",
            "platform": "github",
            "profile_url": "https://github.com/octocat",
            "display_name": "Octo Cat",
        },
        "behavioral_intelligence": {
            "followers": 12,
            "public_repos": 5,
            "platform_presence": ["github"],
            "contribution_score": 20,
            "digital_activity_score": 40,
        },
        "situational_intelligence": {"country": "UK"},
        "metadata": {
            "source": "public_github",
            "collection_date": "2026-05-29T00:00:00+00:00",
            "country": "UK",
            "data_type": "public_signal",
        },
        "raw_signals": {"github_search": {"login": "octocat", "profile_url": "https://github.com/octocat"}},
    }


def _npm_package_profile() -> dict:
    return {
        "stratum_id": "STRID-PIPE02",
        "identity_anchors": {
            "handle": "left-pad",
            "platform": "npm",
            "profile_url": "https://www.npmjs.com/package/left-pad",
        },
        "metadata": {"source": "public_npm", "collection_date": "2026-05-29T00:00:00+00:00"},
        "raw_signals": {
            "npm_search_result": {
                "package": {
                    "name": "left-pad",
                    "maintainers": [{"username": "octocat", "url": "https://github.com/octocat"}],
                }
            },
            "person_link_candidates": [
                {
                    "platform": "github",
                    "handle": "octocat",
                    "profile_url": "https://github.com/octocat",
                    "evidence_type": "github_profile",
                    "source_field": "package.maintainers.url",
                }
            ],
        },
    }


def test_export_pipeline_statistics_fields():
    result = build_job_export([_github_profile(), _npm_package_profile()], job_id="job-test")
    stats = result["statistics"]
    assert "verified_people" in stats
    assert "verification_rate" in stats
    assert "person_profile_ratio" in stats
    assert "average_verification_confidence" in stats
    assert stats["verified_people"] >= 1
    assert result["person_derivation_report"]["persons_derived"] >= 0
    profiles = result["profiles"]
    assert profiles[0]["export_tier"] == "verified_person"


def test_build_export_statistics_average_confidence():
    profiles = prioritize_export_profiles([verify_profile(_github_profile())])
    stats = build_export_statistics(profiles)
    assert stats["average_verification_confidence"] > 0
