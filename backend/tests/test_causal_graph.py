import pytest

from backend.services.causal_functor import (
    build_causal_model,
    create_causal_object,
    link_objects,
    update_causal_model,
    validate_object,
)
from backend.services.causal_functor.models import CausalEvidence, CausalGraph


def _profile(stratum_id: str = "STRID-GRAPH1") -> dict:
    return {
        "stratum_id": stratum_id,
        "identity_anchors": {"handle": "graph-user", "platform": "github"},
        "metadata": {"source": "public_github"},
        "situational_intelligence": {"country": "UK"},
        "behavioral_intelligence": {"tech_stack": ["Python"]},
        "risk_profile": {"overall_risk": "LOW"},
    }


def test_graph_construction_and_validation():
    graph = build_causal_model(stratum_entities=[_profile()])

    assert "stratum_identity:strid_graph1" in graph.objects
    assert graph.validate()["valid"]
    assert graph.detect_cycles() == ()
    assert graph.to_dict()["counts"]["relations"] == len(graph.relations)


def test_graph_traversal_ancestors_descendants_and_confidence():
    graph = CausalGraph()
    a = graph.add_object(create_causal_object("node", "A"))
    b = graph.add_object(create_causal_object("node", "B"))
    c = graph.add_object(create_causal_object("node", "C"))
    evidence = CausalEvidence("ev:g", "manual", "manual", "graph evidence")
    first = link_objects(graph, a.id, b.id, "causes", confidence=0.5, evidence=evidence)
    second = link_objects(graph, b.id, c.id, "enables", confidence=0.5, evidence=evidence)

    assert graph.traverse(a.id)[c.id] == (first.id, second.id)
    assert graph.descendants(a.id)[c.id] == (first.id, second.id)
    assert graph.ancestors(c.id)[a.id] == (second.id, first.id)
    assert graph.propagate_confidence(a.id)[c.id] == 0.25


def test_cycle_detection_and_neighbor_errors():
    graph = CausalGraph()
    a = graph.add_object(create_causal_object("node", "A"))
    b = graph.add_object(create_causal_object("node", "B"))
    link_objects(graph, a.id, b.id, "causes")
    link_objects(graph, b.id, a.id, "causes")

    assert graph.detect_cycles()
    assert graph.validate()["cycle_count"] >= 1
    with pytest.raises(ValueError):
        graph.neighbors("missing")


def test_update_causal_model_adds_new_sources():
    graph = build_causal_model(stratum_entities=[_profile("STRID-GRAPH1")])
    update_causal_model(
        graph,
        stratum_entities=[_profile("STRID-GRAPH2")],
        cognitive_memory_facts=["Graph memory fact"],
    )

    assert "stratum_identity:strid_graph2" in graph.objects
    assert any(obj.source == "memory" for obj in graph.objects.values())
    assert validate_object(graph.objects["stratum_identity:strid_graph2"])
