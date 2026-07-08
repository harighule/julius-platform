from backend.services.causal_functor import (
    backward_inference,
    build_causal_model,
    causal_chain,
    create_causal_object,
    explanation_generation,
    forward_inference,
    link_objects,
)
from backend.services.causal_functor.models import CausalGraph


def _graph() -> CausalGraph:
    graph = CausalGraph()
    a = graph.add_object(create_causal_object("node", "A"))
    b = graph.add_object(create_causal_object("node", "B"))
    c = graph.add_object(create_causal_object("node", "C"))
    link_objects(graph, a.id, b.id, "causes", confidence=0.8)
    link_objects(graph, b.id, c.id, "enables", confidence=0.5)
    return graph


def test_multi_hop_causal_chain_generation():
    graph = _graph()

    chains = causal_chain(graph, "node:a", "node:c")

    assert len(chains) == 1
    assert graph.relation_chain_confidence(chains[0]) == 0.4


def test_forward_and_backward_inference_track_evidence_and_explain():
    graph = _graph()
    forward = forward_inference(graph, "node:a")
    backward = backward_inference(graph, "node:c")

    assert forward.direction == "forward"
    assert backward.direction == "backward"
    assert forward.chains
    assert backward.chains
    assert "Causal explanation:" in forward.explanation
    assert explanation_generation(forward, graph) == forward.explanation


def test_inference_for_missing_objects_is_empty_result():
    graph = _graph()

    assert causal_chain(graph, "missing", "node:c") == ()
    assert forward_inference(graph, "missing").confidence == 0.0
    assert backward_inference(graph, "missing").explanation == "No causal chain was found for the query."


def test_inference_over_built_model_from_upstream_shapes():
    graph = build_causal_model(
        stratum_entities=[
            {
                "stratum_id": "STRID-INF1",
                "identity_anchors": {"platform": "github"},
                "metadata": {"source": "public_github"},
                "behavioral_intelligence": {"tech_stack": ["Python"]},
            }
        ],
        csie_outputs={
            "classifications": [
                {
                    "stratum_id": "STRID-INF1",
                    "uncertainty_level": "LOW",
                    "global_section_summary": {"concept_ids": ["identity:strid_inf1"]},
                }
            ]
        },
    )

    result = forward_inference(graph, "stratum_identity:strid_inf1")

    assert result.confidence > 0
    assert result.evidence_ids
