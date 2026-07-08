import pytest

from backend.services.causal_functor import (
    IdentityMorphism,
    KMorphism,
    MorphismComposition,
    MorphismValidation,
    create_causal_object,
    link_objects,
)
from backend.services.causal_functor.models import CausalGraph


def test_identity_morphism_and_identity_laws():
    identity = IdentityMorphism("a").as_k_morphism()
    morphism = KMorphism("m:a:b", 1, "a", "b", "causes", 0.6)

    assert identity.is_identity
    assert MorphismComposition.compose(identity, morphism) is morphism
    assert MorphismComposition.compose(morphism, IdentityMorphism("b").as_k_morphism()) is morphism


def test_morphism_composition_serialization_and_validation():
    first = KMorphism("m1", 1, "a", "b", "causes", 0.8, ["ctx1"], ["ev1"])
    second = KMorphism("m2", 2, "b", "c", "enables", 0.5, ["ctx2"], ["ev2"])
    composed = MorphismComposition.compose(first, second)

    assert composed.k == 2
    assert composed.source_id == "a"
    assert composed.target_id == "c"
    assert composed.confidence == 0.4
    assert composed.context_ids == ("ctx1", "ctx2")
    assert MorphismComposition.serialize(composed)["id"] == composed.id
    assert MorphismComposition.serialize_many([first, composed])[1]["target_id"] == "c"
    assert MorphismValidation.validate_morphism(composed)["valid"]


def test_morphism_validation_against_graph_and_diagnostics():
    graph = CausalGraph()
    a = graph.add_object(create_causal_object("node", "A"))
    b = graph.add_object(create_causal_object("node", "B"))
    relation = link_objects(graph, a.id, b.id, "causes")
    morphism = KMorphism("m1", 1, a.id, b.id, "causes", 0.7)
    relation_morphism = KMorphism("m2", 2, relation.id, relation.id, "identity", 1.0)

    assert MorphismValidation.validate_morphism(morphism, graph)["valid"]
    assert MorphismValidation.validate_morphism(relation_morphism, graph)["valid"]
    diagnostics = MorphismValidation.diagnostics([morphism, IdentityMorphism(a.id).as_k_morphism()])
    assert diagnostics["morphism_count"] == 2
    assert diagnostics["identity_count"] == 1
    assert diagnostics["by_k"] == {1: 2}


def test_non_composable_morphisms_fail():
    with pytest.raises(ValueError):
        MorphismComposition.compose(
            KMorphism("m1", 1, "a", "b", "causes"),
            KMorphism("m2", 1, "c", "d", "causes"),
        )

    with pytest.raises(ValueError):
        KMorphism("bad", 0, "a", "b", "causes")
