from backend.services.stratum_omnis.csie_bootstrap import (
    build_csie_from_profiles,
    convert_profile_to_csie,
)
from backend.services.stratum_omnis.csie_category import Category
from backend.services.stratum_omnis.csie_sheaf import SheafStore


def _profile(stratum_id: str = "STRID-TEST1") -> dict:
    return {
        "stratum_id": stratum_id,
        "identity_anchors": {
            "handle": "alice",
            "platform": "github",
        },
        "metadata": {
            "source": "public_github",
        },
        "situational_intelligence": {
            "country": "UK",
        },
        "behavioral_intelligence": {
            "tech_stack": ["Python", "FastAPI"],
        },
        "risk_profile": {
            "overall_risk": "LOW",
        },
    }


def test_convert_profile_to_csie_creates_category_objects_morphisms_and_sections():
    category = Category()
    sheaf = SheafStore(embedding_dim=16)

    result = convert_profile_to_csie(_profile(), category, sheaf)

    assert result.stratum_id == "STRID-TEST1"
    assert result.identity_object_id == "identity:strid_test1"
    assert "identity:strid_test1" in category.objects
    assert "platform:github" in category.objects
    assert "source:public_github" in category.objects
    assert "country:uk" in category.objects
    assert "risk:low" in category.objects
    assert "tech:python" in category.objects
    assert "tech:fastapi" in category.objects
    assert result.morphism_ids
    assert all(morphism_id in category.morphisms for morphism_id in result.morphism_ids)
    assert "ctx:root:global" in result.context_ids
    assert "ctx:platform:github" in result.context_ids
    assert result.section_ids
    for ctx_id, concept_id in result.section_ids:
        assert concept_id in sheaf.sections(ctx_id)


def test_build_csie_from_profiles_is_deterministic_and_idempotent_for_duplicate_profiles():
    profiles = [_profile("STRID-TEST1"), _profile("STRID-TEST1")]

    result = build_csie_from_profiles(profiles, embedding_dim=16)

    assert len(result.conversions) == 2
    assert len(result.category.objects) == 7
    assert len(result.category.morphisms) == 6
    assert result.conversions[0].context_ids == result.conversions[1].context_ids
    assert result.conversions[0].morphism_ids == result.conversions[1].morphism_ids


def test_profile_conversion_handles_missing_optional_fields_safely():
    category = Category()
    sheaf = SheafStore(embedding_dim=16)

    result = convert_profile_to_csie({"stratum_id": "STRID-MIN"}, category, sheaf)

    assert result.identity_object_id == "identity:strid_min"
    assert result.context_ids == ("ctx:root:global",)
    assert result.morphism_ids == ()
    assert result.section_ids == ()


def test_profile_contexts_can_be_used_for_neighbor_retrieval_and_covering():
    result = build_csie_from_profiles([_profile()], embedding_dim=16)
    sheaf = result.sheaf
    github_context = sheaf.contexts["ctx:platform:github"]

    nearest = sheaf.find_nearest(github_context.activation_signature, k=1)
    covering = sheaf.get_covering(["ctx:platform:github"])

    assert nearest == ["ctx:platform:github"]
    assert covering == ["ctx:platform:github", "ctx:root:global"]

