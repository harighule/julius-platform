"""Diagnostics for the Causal Functor core."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable

from .causal_models import build_causal_model, export_causal_model
from .inference import backward_inference, causal_chain, explanation_generation, forward_inference
from .models import CausalGraph, CausalInferenceResult
from .morphisms import MorphismValidation

logger = logging.getLogger(__name__)


def graph_statistics(graph: CausalGraph) -> dict[str, Any]:
    root_count = sum(1 for obj_id in graph.objects if not graph.incoming.get(obj_id))
    leaf_count = sum(1 for obj_id in graph.objects if not graph.outgoing.get(obj_id))
    out_degrees = [len(relations) for relations in graph.outgoing.values()]
    return {
        "object_count": len(graph.objects),
        "relation_count": len(graph.relations),
        "evidence_count": len(graph.evidence),
        "root_count": root_count,
        "leaf_count": leaf_count,
        "cycle_count": len(graph.detect_cycles()),
        "max_out_degree": max(out_degrees) if out_degrees else 0,
    }


def morphism_statistics(graph: CausalGraph) -> dict[str, Any]:
    relation_types = Counter(relation.relation_type for relation in graph.relations.values())
    source_types = Counter(obj.source for obj in graph.objects.values())
    return {
        "relation_types": dict(sorted(relation_types.items())),
        "object_sources": dict(sorted(source_types.items())),
        "average_relation_confidence": _average(
            relation.confidence for relation in graph.relations.values()
        ),
    }


def inference_metrics(results: Iterable[CausalInferenceResult]) -> dict[str, Any]:
    result_list = tuple(results)
    return {
        "result_count": len(result_list),
        "chain_count": sum(len(result.chains) for result in result_list),
        "average_confidence": _average(result.confidence for result in result_list),
    }


def validation_reports(graph: CausalGraph) -> dict[str, Any]:
    report = MorphismValidation.validate_graph(graph)
    graph_report = graph.validate()
    return {
        "valid": report["valid"] and graph_report["valid"],
        "error_count": len(report["errors"]) + graph_report["error_count"],
        "errors": [*report["errors"], *graph_report["errors"]],
        "cycle_count": graph_report["cycle_count"],
    }


def build_live_causal_graph(limit: int = 10) -> CausalGraph:
    safe_limit = max(1, min(int(limit), 50))
    from ..stratum_omnis.csie import get_csie_snapshot
    from ..stratum_omnis.profile_store import load_stratum_profiles

    profiles = load_stratum_profiles(safe_limit)
    csie = get_csie_snapshot(safe_limit)
    return build_causal_model(
        stratum_entities=profiles,
        csie_outputs=csie,
        workflow_results=_load_workflow_results(safe_limit),
        cognitive_memory_facts=_load_memory_facts(safe_limit),
    )


def get_causal_functor_diagnostics(limit: int = 10) -> dict[str, Any]:
    """Build a live Causal Functor diagnostic snapshot from existing services."""

    graph = build_live_causal_graph(limit)
    samples = [
        forward_inference(graph, object_id, max_depth=2)
        for object_id in list(graph.objects)[:3]
    ]
    diagnostics = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "causal_functor_engine": {
            "mode": "causal_functor_core",
            "version": "core_v1",
            "available": True,
            "depends_on": ["stratum", "csie"],
        },
        "graph_statistics": graph_statistics(graph),
        "morphism_statistics": morphism_statistics(graph),
        "inference_metrics": inference_metrics(samples),
        "validation_report": validation_reports(graph),
        "sample_inferences": [sample.to_dict() for sample in samples],
        "causal_model": export_causal_model(graph),
    }
    logger.info(
        "Generated Causal Functor diagnostics with %s objects",
        diagnostics["graph_statistics"]["object_count"],
    )
    return diagnostics


def get_causal_functor_graph(limit: int = 10) -> dict[str, Any]:
    graph = build_live_causal_graph(limit)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "causal_functor_engine": {
            "mode": "causal_functor_core",
            "version": "core_v1",
            "available": True,
        },
        **export_causal_model(graph),
        "graph_statistics": graph_statistics(graph),
        "validation_report": validation_reports(graph),
    }


def get_causal_functor_inference(
    *,
    source_id: str | None = None,
    target_id: str | None = None,
    direction: str = "forward",
    limit: int = 10,
    max_depth: int = 3,
) -> dict[str, Any]:
    graph = build_live_causal_graph(limit)
    object_ids = list(graph.objects)
    if not object_ids:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "causal_functor_engine": {
                "mode": "causal_functor_core",
                "version": "core_v1",
                "available": True,
            },
            "result": None,
            "message": "No causal objects are available for inference.",
        }
    start_id = source_id if source_id in graph.objects else object_ids[0]
    if target_id and target_id in graph.objects:
        chains = causal_chain(graph, start_id, target_id, max_depth=max_depth)
        result = CausalInferenceResult(
            query=f"chain:{start_id}:{target_id}",
            direction="chain",
            source_id=start_id,
            target_id=target_id,
            chains=chains,
            confidence=_average(
                graph.relation_chain_confidence(chain) for chain in chains
            ),
            evidence_ids=_evidence_for_chains(graph, chains),
        )
        result.explanation = explanation_generation(result, graph)
    elif direction == "backward":
        result = backward_inference(graph, start_id, max_depth=max_depth)
    else:
        result = forward_inference(graph, start_id, max_depth=max_depth)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "causal_functor_engine": {
            "mode": "causal_functor_core",
            "version": "core_v1",
            "available": True,
        },
        "result": result.to_dict(),
        "graph_statistics": graph_statistics(graph),
    }


def _average(values: Iterable[float]) -> float:
    value_list = [float(value) for value in values]
    if not value_list:
        return 0.0
    return sum(value_list) / len(value_list)


def _evidence_for_chains(
    graph: CausalGraph,
    chains: Iterable[tuple[str, ...]],
) -> tuple[str, ...]:
    evidence_ids: set[str] = set()
    for chain in chains:
        for relation_id in chain:
            relation = graph.relations.get(relation_id)
            if relation is not None:
                evidence_ids.update(relation.evidence_ids)
    return tuple(sorted(evidence_ids))


def _load_workflow_results(limit: int) -> list[dict[str, Any]]:
    try:
        from ...database import db

        workflows = db.get_workflows()[:limit]
        results: list[dict[str, Any]] = []
        for workflow in workflows:
            workflow_id = workflow.get("id")
            if workflow_id is None:
                continue
            with_steps = db.get_workflow_with_steps(int(workflow_id)) or workflow
            results.append(with_steps)
        return results
    except Exception as exc:
        logger.debug("Causal Functor workflow ingestion skipped: %s", exc)
        return []


def _load_memory_facts(limit: int) -> list[dict[str, Any]]:
    try:
        from ...database import db

        return db.knowledge_all(limit)
    except Exception as exc:
        logger.debug("Causal Functor memory ingestion skipped: %s", exc)
        return []
