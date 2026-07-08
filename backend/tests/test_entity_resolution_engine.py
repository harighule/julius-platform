from backend.services.stratum_omnis.entity_resolution_engine import (
    apply_canonical_resolution,
    registered_domain,
    resolve_profile,
)


def test_registered_domain_handles_uk_second_level_domains():
    assert registered_domain("api.service.gov.uk") == "service.gov.uk"
    assert registered_domain("www.example.co.uk") == "example.co.uk"


def test_github_profile_gets_stable_developer_entity_key():
    profile = {
        "stratum_id": "STRID-ENTITY1",
        "identity_anchors": {
            "handle": "OctoCat-UK",
            "platform": "github",
            "resolution_confidence": 0.72,
            "profile_url": "https://github.com/OctoCat-UK",
        },
        "situational_intelligence": {"org": ""},
        "network_signals": {"hostnames": []},
        "metadata": {"source": "public_github", "data_type": "public_signal"},
        "raw_signals": {"github_search": {"login": "OctoCat-UK"}},
    }

    resolved = resolve_profile(profile)
    assert resolved.canonical_entity_key == "developer:github:octocat-uk"
    assert resolved.entity_type == "digital_identity"
    assert resolved.resolution_confidence >= 0.8


def test_apply_canonical_resolution_is_schema_additive():
    profile = {
        "stratum_id": "STRID-ENTITY2",
        "identity_anchors": {
            "handle": "Example Agency procurement notice",
            "platform": "public_spending_context",
            "resolution_confidence": 0.6,
            "profile_url": "https://www.gov.uk/example-agency/procurement",
        },
        "situational_intelligence": {"org": "Example Agency"},
        "network_signals": {"hostnames": ["www.gov.uk"]},
        "metadata": {"source": "public_spending_context", "data_type": "public_signal"},
        "raw_signals": {"public_spending_context": {"matched_terms": ["procurement"]}},
    }

    enriched = apply_canonical_resolution(profile)
    identity = enriched["identity_anchors"]
    assert enriched["entity_resolution"]["canonical_entity_key"] == "organization:example-agency"
    assert identity["canonical_entity_key"] == "organization:example-agency"
    assert identity["entity_type"] == "organization"
    assert identity["resolution_confidence"] >= 0.8
