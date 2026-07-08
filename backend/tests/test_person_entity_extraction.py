"""Tests for person entity derivation from public artifact signals."""

from backend.services.person_entity_extraction import (
    derive_person_profiles,
    parse_public_profile_url,
)
from backend.services.person_verification import (
    classify_entity_type,
    merge_canonical_entities,
    prioritize_export_profiles,
    verify_profile,
)


def _npm_artifact_with_github_maintainer() -> dict:
    return {
        "stratum_id": "STRID-NPM001",
        "identity_anchors": {
            "handle": "left-pad",
            "platform": "npm",
            "profile_url": "https://www.npmjs.com/package/left-pad",
        },
        "metadata": {
            "source": "public_npm",
            "collection_date": "2026-05-29T00:00:00+00:00",
            "country": "UK",
            "data_type": "public_signal",
        },
        "raw_signals": {
            "npm_search_result": {
                "package": {
                    "name": "left-pad",
                    "maintainers": [
                        {
                            "username": "octocat",
                            "url": "https://github.com/octocat",
                        }
                    ],
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
        },
    }


def _pypi_artifact_author_text_only() -> dict:
    return {
        "stratum_id": "STRID-PYPI001",
        "identity_anchors": {"handle": "django", "platform": "pypi"},
        "metadata": {"source": "public_pypi", "collection_date": "2026-05-29T00:00:00+00:00"},
        "raw_signals": {
            "pypi_info": {
                "name": "django",
                "author": "Django Software Foundation",
                "maintainer": "No URL Author",
            },
            "person_link_candidates": [],
        },
    }


def test_parse_github_profile_url():
    ref = parse_public_profile_url("https://github.com/octocat")
    assert ref is not None
    assert ref.platform == "github"
    assert ref.handle == "octocat"


def test_does_not_invent_github_from_display_name():
    assert parse_public_profile_url("https://github.com/Jane%20Doe") is None


def test_derive_person_from_npm_maintainer_github_url():
    artifact = _npm_artifact_with_github_maintainer()
    expanded, report = derive_person_profiles([artifact])
    assert report["persons_derived"] == 1
    person = next(p for p in expanded if p["metadata"]["source"] == "derived_public_person")
    assert person["identity_anchors"]["profile_url"] == "https://github.com/octocat"
    assert person["public_identity_evidence"][0]["url"] == "https://github.com/octocat"


def test_pypi_author_text_only_does_not_create_person():
    expanded, report = derive_person_profiles([_pypi_artifact_author_text_only()])
    assert report["persons_derived"] == 0


def test_merge_github_artifact_and_direct_profile():
    artifact = _npm_artifact_with_github_maintainer()
    direct = {
        "stratum_id": "STRID-GH001",
        "identity_anchors": {
            "handle": "octocat",
            "platform": "github",
            "profile_url": "https://github.com/octocat",
            "display_name": "Octo Cat",
        },
        "behavioral_intelligence": {"followers": 10, "public_repos": 5, "platform_presence": ["github"]},
        "metadata": {"source": "public_github", "collection_date": "2026-05-29T00:00:00+00:00"},
        "raw_signals": {},
    }
    expanded, _ = derive_person_profiles([artifact, direct])
    merged, report = merge_canonical_entities(expanded)
    assert report["canonical_entities"] == 2
    person = next(p for p in merged if (p.get("verification") or {}).get("is_real_person"))
    assert person["verification"]["entity_type"] == "person"
    assert "https://github.com/octocat" in person["verification"]["public_profile_links"]


def test_prioritize_verified_person_before_artifact():
    artifact = verify_profile(_npm_artifact_with_github_maintainer())
    expanded, _ = derive_person_profiles([_npm_artifact_with_github_maintainer()])
    person = verify_profile(next(p for p in expanded if p["metadata"]["source"] == "derived_public_person"))
    ordered = prioritize_export_profiles([artifact, person])
    assert ordered[0]["export_tier"] == "verified_person"
    assert ordered[-1]["export_tier"] in {"artifact", "document", "other"}
