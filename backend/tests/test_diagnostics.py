from backend.services.causal_functor import (
    build_causal_model,
    get_causal_functor_diagnostics,
    get_causal_functor_graph,
    get_causal_functor_inference,
    graph_statistics,
    inference_metrics,
    morphism_statistics,
    validation_reports,
)
from backend.services.causal_functor.inference import forward_inference


def _graph():
    return build_causal_model(
        stratum_entities=[
            {
                "stratum_id": "STRID-DIAG1",
                "identity_anchors": {"platform": "github"},
                "metadata": {"source": "public_github"},
                "risk_profile": {"overall_risk": "LOW"},
            }
        ],
        csie_outputs={
            "classifications": [
                {
                    "stratum_id": "STRID-DIAG1",
                    "uncertainty_level": "LOW",
                    "global_section_summary": {"concept_ids": ["identity:strid_diag1"]},
                }
            ]
        },
    )


def test_graph_morphism_inference_and_validation_diagnostics():
    graph = _graph()
    result = forward_inference(graph, "stratum_identity:strid_diag1")

    assert graph_statistics(graph)["cycle_count"] == 0
    assert morphism_statistics(graph)["average_relation_confidence"] > 0
    assert inference_metrics([result])["chain_count"] >= 1
    assert validation_reports(graph)["valid"]


def test_live_diagnostic_helpers_are_serializable(monkeypatch):
    import backend.services.causal_functor.diagnostics as diagnostics

    monkeypatch.setattr(diagnostics, "_load_workflow_results", lambda limit: [])
    monkeypatch.setattr(diagnostics, "_load_memory_facts", lambda limit: [])
    monkeypatch.setattr(
        "backend.services.stratum_omnis.profile_store.load_stratum_profiles",
        lambda limit: [],
    )
    monkeypatch.setattr(
        "backend.services.stratum_omnis.csie.get_csie_snapshot",
        lambda limit: {"classifications": []},
    )

    diag = get_causal_functor_diagnostics(limit=1)
    graph = get_causal_functor_graph(limit=1)
    inference = get_causal_functor_inference(limit=1)

    assert diag["causal_functor_engine"]["mode"] == "causal_functor_core"
    assert graph["causal_graph"]["counts"]["objects"] == 0
    assert inference["result"] is None


def test_requested_api_endpoints(client):
    diagnostics_resp = client.get("/diagnostics/causal-functor?limit=1")
    graph_resp = client.get("/causal-functor/graph?limit=1")
    inference_resp = client.get("/causal-functor/inference?limit=1")

    assert diagnostics_resp.status_code == 200
    assert graph_resp.status_code == 200
    assert inference_resp.status_code == 200
    assert "graph_statistics" in diagnostics_resp.json()
    assert "causal_graph" in graph_resp.json()
    assert "causal_functor_engine" in inference_resp.json()
