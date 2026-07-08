import pytest

from backend.services.causal_functor import (
    IdentityMorphism,
    KMorphism,
    MorphismComposition,
    MorphismValidation,
    backward_inference,
    build_causal_model,
    causal_chain,
    create_causal_object,
    export_causal_model,
    forward_inference,
    graph_statistics,
    inference_metrics,
    link_objects,
    morphism_statistics,
    validate_object,
    validation_reports,
)
from backend.services.causal_functor.models import CausalEvidence, CausalGraph


def _profile() -> dict:
    return {
        "stratum_id": "STRID-CAUSE1",
        "identity_anchors": {"handle": "cause-user", "platform": "github"},
        "metadata": {"source": "public_github"},
        "situational_intelligence": {"country": "UK"},
        "behavioral_intelligence": {"tech_stack": ["Python"]},
        "risk_profile": {"overall_risk": "LOW"},
    }


def _csie_output() -> dict:
    return {
        "classifications": [
            {
                "stratum_id": "STRID-CAUSE1",
                "uncertainty_level": "LOW",
                "h1_residual": 0.0,
                "global_section_summary": {
                    "count": 1,
                    "concept_ids": ["identity:strid_cause1"],
                },
                "diagnostics": {
                    "global_section_count": 1,
                    "conflict_count": 0,
                    "knowledge_gap_count": 0,
                    "polysemy_count": 0,
                    "uncertainty": "LOW",
                },
            }
        ]
    }


def test_object_creation_and_linking():
    graph = CausalGraph()
    source = graph.add_object(create_causal_object("entity", "Alice", source="manual"))
    target = graph.add_object(create_causal_object("state", "Alert", object_type="state"))
    evidence = CausalEvidence(
        id="ev:manual:alert",
        source_type="manual",
        source_id="manual",
        description="Manual test evidence",
    )

    assert validate_object(source)
    relation = link_objects(
        graph,
        source.id,
        target.id,
        "causes",
        confidence=1.2,
        evidence=evidence,
    )

    assert relation.confidence == 1.0
    assert graph.outgoing[source.id] == [relation.id]
    assert graph.incoming[target.id] == [relation.id]
    assert graph.evidence[evidence.id] == evidence


def test_morphism_validation_and_composition():
    first = KMorphism("m1", 1, "a", "b", "causes", 0.8)
    second = KMorphism("m2", 1, "b", "c", "enables", 0.5)
    composed = MorphismComposition.compose(first, second)
    identity = IdentityMorphism("a").as_k_morphism()

    assert composed.source_id == "a"
    assert composed.target_id == "c"
    assert composed.confidence == 0.4
    assert identity.source_id == identity.target_id == "a"
    assert MorphismValidation.validate_morphism(composed)["valid"]

    with pytest.raises(ValueError):
        MorphismComposition.compose(second, first)


def test_graph_construction_reuses_stratum_and_csie_shapes():
    graph = build_causal_model(
        stratum_entities=[_profile()],
        csie_outputs=_csie_output(),
        workflow_results=[{"workflow_id": 7, "status": "completed", "open_ports": 2}],
        cognitive_memory_facts=[{"fact": "Host produced a low-risk signal", "confidence": 0.8}],
    )
    exported = export_causal_model(graph)

    assert exported["engine"]["mode"] == "causal_functor_core"
    assert "stratum_identity:strid_cause1" in graph.objects
    assert "csie_classification:strid_cause1" in graph.objects
    assert any(relation.relation_type == "explained_by" for relation in graph.relations.values())
    assert any(obj.source == "workflow" for obj in graph.objects.values())
    assert any(obj.source == "memory" for obj in graph.objects.values())
    assert validation_reports(graph)["valid"]


def test_inference_execution_and_chain_explanations():
    graph = build_causal_model(stratum_entities=[_profile()], csie_outputs=_csie_output())
    source_id = "stratum_identity:strid_cause1"
    target_id = "csie_classification:strid_cause1"

    chains = causal_chain(graph, source_id, target_id)
    forward = forward_inference(graph, source_id)
    backward = backward_inference(graph, target_id)

    assert chains
    assert forward.chains
    assert backward.chains
    assert forward.confidence > 0
    assert "Causal explanation:" in forward.explanation


def test_diagnostics_and_metrics():
    graph = build_causal_model(stratum_entities=[_profile()], csie_outputs=_csie_output())
    forward = forward_inference(graph, "stratum_identity:strid_cause1")

    stats = graph_statistics(graph)
    morphisms = morphism_statistics(graph)
    metrics = inference_metrics([forward])
    validation = validation_reports(graph)

    assert stats["object_count"] >= 2
    assert stats["relation_count"] >= 1
    assert morphisms["relation_types"]
    assert metrics["result_count"] == 1
    assert validation["valid"]


def test_causal_functor_diagnostics_endpoint(client):
    resp = client.get("/api/stratum/causal-functor/diagnostics?limit=1")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["causal_functor_engine"]["mode"] == "causal_functor_core"
    assert "graph_statistics" in payload
    assert "morphism_statistics" in payload
    assert "inference_metrics" in payload
    assert "validation_report" in payload
