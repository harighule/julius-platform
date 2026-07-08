"""Tests for person-centric relationship graph."""

from backend.services.export_pipeline import build_job_export
from backend.services.person_relationship_graph import build_relationship_graph
from backend.services.person_verification import verify_profile


def _npm_with_maintainer() -> dict:
    return {
        "stratum_id": "STRID-REL-NPM",
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
                    "links": {"repository": "https://github.com/octocat/left-pad"},
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
            "contributor_page_candidates": [
                {
                    "platform": "github",
                    "handle": "octocat/left-pad",
                    "profile_url": "https://github.com/octocat/left-pad/graphs/contributors",
                    "evidence_type": "github_contributors_page",
                    "repository_url": "https://github.com/octocat/left-pad",
                }
            ],
        },
    }


def _github_person() -> dict:
    return verify_profile(
        {
            "stratum_id": "STRID-REL-GH",
            "identity_anchors": {
                "handle": "octocat",
                "platform": "github",
                "profile_url": "https://github.com/octocat",
            },
            "behavioral_intelligence": {"followers": 5, "public_repos": 2, "platform_presence": ["github"]},
            "metadata": {"source": "public_github", "collection_date": "2026-05-29T00:00:00+00:00"},
            "raw_signals": {},
        }
    )


def test_relationship_graph_package_link():
    export = build_job_export([_npm_with_maintainer(), _github_person()], job_id="rel-test")
    graph = export["relationship_graph"]
    assert graph["summary"]["edge_count"] >= 1
    person = export["person_profiles"][0]
    rel = person.get("relationship_graph") or {}
    assert len(rel.get("packages") or []) >= 1 or len(rel.get("contributor_profiles") or []) >= 1
    types = graph["summary"].get("relationship_types") or []
    assert any(t in types for t in ("maintains_package", "has_contributor_profile"))


def test_export_includes_person_profiles_and_stats():
    export = build_job_export([_npm_with_maintainer(), _github_person()], job_id="rel-test")
    assert "person_profiles" in export
    assert "relationship_graph" in export
    stats = export["statistics"]
    assert "verified_people" in stats
    assert "verification_rate" in stats
    assert "person_profile_ratio" in stats
    assert "source_distribution" in stats
    assert stats["primary_export_object"] == "verified_person"
    assert export["person_profiles"][0]["export_tier"] == "verified_person"
