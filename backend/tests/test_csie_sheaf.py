import pytest

from backend.services.stratum_omnis.csie_sheaf import (
    ContextStore,
    SectionStore,
    SheafStore,
    context_id,
    cosine_similarity,
    deterministic_vector,
)
from backend.services.stratum_omnis.csie_types import ContextNode, SemanticSection


def test_context_and_section_stores_add_and_retrieve_records():
    contexts = ContextStore()
    sections = SectionStore(contexts)
    ctx = contexts.add(
        ContextNode(
            id="ctx:platform:github",
            description="GitHub context",
            activation_signature=deterministic_vector("github", 8),
        )
    )
    section = sections.add(
        ctx.id,
        "platform:github",
        SemanticSection(
            concept_id="platform:github",
            interpretation=deterministic_vector("platform:github", 8),
            confidence=0.9,
            source_contexts=[ctx.id],
        ),
    )

    assert contexts.require(ctx.id) is ctx
    assert sections.get(ctx.id, "platform:github") is section
    assert sections.sections(ctx.id) == {"platform:github": section}


def test_section_store_rejects_mismatched_concept_id():
    contexts = ContextStore()
    sections = SectionStore(contexts)
    contexts.add(ContextNode("ctx:a", "A"))

    with pytest.raises(ValueError, match="does not match"):
        sections.add(
            "ctx:a",
            "concept:a",
            SemanticSection("concept:b", deterministic_vector("b", 8), 1.0),
        )


def test_sheaf_neighbor_retrieval_is_stable_and_similarity_based():
    sheaf = SheafStore(embedding_dim=8)
    sheaf.add_context(
        ContextNode(
            "ctx:platform:github",
            "GitHub",
            activation_signature=deterministic_vector("github", 8),
        )
    )
    sheaf.add_context(
        ContextNode(
            "ctx:platform:gitlab",
            "GitLab",
            activation_signature=deterministic_vector("gitlab", 8),
        )
    )

    nearest = sheaf.find_nearest(deterministic_vector("github", 8), k=1)

    assert nearest == ["ctx:platform:github"]


def test_get_covering_includes_parent_contexts_once():
    sheaf = SheafStore(embedding_dim=8)
    sheaf.add_context(ContextNode("ctx:root:global", "Global"))
    sheaf.add_context(
        ContextNode(
            "ctx:platform:github",
            "GitHub",
            parent_contexts=["ctx:root:global"],
        )
    )

    assert sheaf.get_covering(["ctx:platform:github", "ctx:platform:github"]) == [
        "ctx:platform:github",
        "ctx:root:global",
    ]
    assert sheaf.contexts["ctx:root:global"].child_contexts == ("ctx:platform:github",)


def test_gluing_validation_passes_for_matching_sections():
    sheaf = SheafStore(embedding_dim=8)
    vec = deterministic_vector("same", 8)
    for ctx_id in ["ctx:a", "ctx:b"]:
        sheaf.add_context(ContextNode(ctx_id, ctx_id))
        sheaf.add_section(
            ctx_id,
            "concept:x",
            SemanticSection("concept:x", vec, 1.0, [ctx_id]),
        )

    validation = sheaf.validate_gluing("ctx:a", "ctx:b", threshold=0.7)

    assert validation.passed
    assert validation.similarities["concept:x"] == pytest.approx(1.0)
    assert validation.violations == {}


def test_gluing_validation_flags_divergent_sections():
    sheaf = SheafStore(embedding_dim=8)
    sheaf.add_context(ContextNode("ctx:a", "A"))
    sheaf.add_context(ContextNode("ctx:b", "B"))
    sheaf.add_section(
        "ctx:a",
        "concept:x",
        SemanticSection("concept:x", (1, 0, 0, 0, 0, 0, 0, 0), 1.0, ["ctx:a"]),
    )
    sheaf.add_section(
        "ctx:b",
        "concept:x",
        SemanticSection("concept:x", (-1, 0, 0, 0, 0, 0, 0, 0), 1.0, ["ctx:b"]),
    )

    validation = sheaf.validate_gluing("ctx:a", "ctx:b", threshold=0.7)

    assert not validation.passed
    assert validation.similarities["concept:x"] == pytest.approx(-1.0)
    assert validation.violations == {"concept:x": pytest.approx(-1.0)}


def test_vector_helpers_are_deterministic_normalized_and_safe():
    vec = deterministic_vector("github", 16)

    assert vec == deterministic_vector("github", 16)
    assert cosine_similarity(vec, vec) == pytest.approx(1.0)
    assert cosine_similarity(vec, []) == 0.0
    assert context_id("Platform", "GitHub / Public") == "ctx:platform:github_public"

