"""Tests for person verification and canonical entity merge."""

from backend.services.person_verification import (
    classify_entity_type,
    merge_canonical_entities,
    verify_profile,
)


def _github_profile(login: str = "octocat") -> dict:
    return {
        "stratum_id": "STRID-TESTGH01",
        "identity_anchors": {
            "handle": login,
            "platform": "github",
            "profile_url": f"https://github.com/{login}",
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
        "raw_signals": {"github_search": {"login": login, "profile_url": f"https://github.com/{login}"}},
    }


def _gdelt_publisher_profile() -> dict:
    return {
        "stratum_id": "STRID-TESTGD01",
        "identity_anchors": {
            "handle": "publisher:bbc.co.uk",
            "platform": "gdelt",
            "profile_url": "https://www.bbc.co.uk/news/article",
        },
        "behavioral_intelligence": {},
        "situational_intelligence": {"country": "UK"},
        "metadata": {
            "source": "public_gdelt",
            "collection_date": "2026-05-29T00:00:00+00:00",
            "country": "UK",
            "data_type": "public_signal",
        },
        "raw_signals": {"gdelt_article": {"url": "https://www.bbc.co.uk/news/article", "title": "UK News"}},
    }


def test_classify_github_as_person():
    assert classify_entity_type(_github_profile()) == "person"


def test_classify_gdelt_as_publisher():
    assert classify_entity_type(_gdelt_publisher_profile()) == "publisher"


def test_verify_github_person_has_evidence():
    verified = verify_profile(_github_profile())
    v = verified["verification"]
    assert v["is_real_person"] is True
    assert v["entity_type"] == "person"
    assert v["evidence_count"] >= 1
    assert len(v["public_profile_links"]) >= 1
    assert len(v.get("public_identity_evidence") or []) >= 1
    assert len(v.get("public_verification_links") or []) >= 1
    assert "public_github" in v["public_identity_sources"] or "github" in v["public_identity_sources"]


def test_merge_deduplicates_same_github_login():
    p1 = _github_profile("same-user")
    p2 = _github_profile("same-user")
    p2["stratum_id"] = "STRID-TESTGH02"

    merged, report = merge_canonical_entities([p1, p2])
    assert report["canonical_entities"] == 1
    assert merged[0]["verification"]["entity_type"] == "person"
    assert merged[0]["verification"]["is_real_person"] is True
    assert merged[0].get("merged_signal_count") == 2


def test_merge_keeps_separate_entity_types():
    merged, report = merge_canonical_entities([_github_profile(), _gdelt_publisher_profile()])
    assert report["canonical_entities"] == 2
    types = {p["verification"]["entity_type"] for p in merged}
    assert types == {"person", "publisher"}
