import pytest

from backend.services.stratum_omnis.csie_category import (
    Category,
    country_object_id,
    make_semantic_object,
    platform_object_id,
    risk_object_id,
    source_object_id,
    tech_stack_object_id,
)
from backend.services.stratum_omnis.csie_types import (
    ContextNode,
    Morphism,
    SemanticObject,
    SemanticSection,
)


def test_core_types_validate_and_coerce_values():
    obj = SemanticObject("platform:github", "concept", [1, 2, 3])
    section = SemanticSection("platform:github", [0.1, 0.2], 1.2, ["ctx"])
    ctx = ContextNode("ctx", "GitHub context", ["parent"], [], {"platform:github": section}, [1])

    assert obj.prototype_vector == (1.0, 2.0, 3.0)
    assert section.confidence == 1.0
    assert section.source_contexts == ("ctx",)
    assert ctx.activation_signature == (1.0,)


def test_object_insertion_is_idempotent():
    category = Category()
    first = category.add_object(make_semantic_object("platform", "GitHub"))
    second = category.add_object(make_semantic_object("platform", "github"))

    assert first is second
    assert list(category.objects) == ["platform:github"]
    assert category.outgoing["platform:github"] == []
    assert category.incoming["platform:github"] == []


def test_morphism_insertion_updates_indexes():
    category = Category()
    category.add_object(make_semantic_object("platform", "github"))
    category.add_object(make_semantic_object("source", "public_github"))

    morphism = category.add_morphism(
        Morphism(
            id="m1",
            source="platform:github",
            target="source:public_github",
            relation_type="related_to",
            weight=0.8,
            context_restriction=["ctx:github"],
        )
    )

    assert category.hom("platform:github", "source:public_github") == [morphism]
    assert category.outgoing["platform:github"] == ["m1"]
    assert category.incoming["source:public_github"] == ["m1"]


def test_morphism_requires_known_objects():
    category = Category()
    category.add_object(make_semantic_object("platform", "github"))

    with pytest.raises(ValueError, match="Unknown morphism target"):
        category.add_morphism(
            Morphism(
                id="m1",
                source="platform:github",
                target="source:missing",
                relation_type="related_to",
                weight=1,
            )
        )


def test_composition_validates_compatibility_and_adds_composed_morphism():
    category = Category()
    for kind, value in [
        ("identity", "alice"),
        ("platform", "github"),
        ("source", "public_github"),
    ]:
        category.add_object(make_semantic_object(kind, value))

    category.add_morphism(
        Morphism("m1", "identity:alice", "platform:github", "is_a", 0.9, ["ctx:a"])
    )
    category.add_morphism(
        Morphism("m2", "platform:github", "source:public_github", "related_to", 0.5, ["ctx:b"])
    )

    composed = category.compose("m1", "m2")

    assert composed.id == "comp:m1:m2"
    assert composed.source == "identity:alice"
    assert composed.target == "source:public_github"
    assert composed.weight == pytest.approx(0.45)
    assert composed.context_restriction == ("ctx:a", "ctx:b")
    assert category.hom("identity:alice", "source:public_github") == [composed]


def test_composition_rejects_non_composable_morphisms():
    category = Category()
    for kind, value in [
        ("identity", "alice"),
        ("platform", "github"),
        ("source", "public_github"),
        ("country", "uk"),
    ]:
        category.add_object(make_semantic_object(kind, value))

    category.add_morphism(Morphism("m1", "identity:alice", "platform:github", "is_a", 1))
    category.add_morphism(Morphism("m2", "source:public_github", "country:uk", "at_location", 1))

    with pytest.raises(ValueError, match="Non-composable"):
        category.compose("m1", "m2")


def test_reachable_returns_expected_paths():
    category = Category()
    for kind, value in [
        ("identity", "alice"),
        ("platform", "github"),
        ("source", "public_github"),
        ("country", "uk"),
    ]:
        category.add_object(make_semantic_object(kind, value))

    category.add_morphism(Morphism("m1", "identity:alice", "platform:github", "is_a", 1))
    category.add_morphism(Morphism("m2", "platform:github", "source:public_github", "related_to", 1))
    category.add_morphism(Morphism("m3", "source:public_github", "country:uk", "at_location", 1))

    depth_two = category.reachable("identity:alice", max_depth=2)
    depth_three = category.reachable("identity:alice", max_depth=3)

    assert depth_two == {
        "identity:alice": [],
        "platform:github": ["m1"],
        "source:public_github": ["m1", "m2"],
    }
    assert depth_three["country:uk"] == ["m1", "m2", "m3"]


def test_deterministic_object_id_helpers_normalize_domain_values():
    assert platform_object_id("GitHub") == "platform:github"
    assert source_object_id("Public GitHub") == "source:public_github"
    assert country_object_id("United Kingdom") == "country:united_kingdom"
    assert tech_stack_object_id("Python / FastAPI") == "tech:python_fastapi"
    assert risk_object_id("LOW") == "risk:low"

