"""Causal model construction from existing JULIUS outputs."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from .causal_objects import create_causal_object, link_objects, normalize_id_part
from .models import CausalEvidence, CausalGraph, CausalObject

logger = logging.getLogger(__name__)


def build_causal_model(
    *,
    stratum_entities: Iterable[dict[str, Any]] | None = None,
    csie_outputs: dict[str, Any] | Iterable[dict[str, Any]] | None = None,
    workflow_results: Iterable[dict[str, Any]] | None = None,
    cognitive_memory_facts: Iterable[str | dict[str, Any]] | None = None,
) -> CausalGraph:
    """Build a causal graph from existing upstream JULIUS layers."""

    graph = CausalGraph()
    for profile in stratum_entities or ():
        _ingest_stratum_profile(graph, profile)
    for classification in _iter_csie_classifications(csie_outputs):
        _ingest_csie_classification(graph, classification)
    for result in workflow_results or ():
        _ingest_workflow_result(graph, result)
    for fact in cognitive_memory_facts or ():
        _ingest_memory_fact(graph, fact)
    logger.info(
        "Built causal model with %s objects, %s relations",
        len(graph.objects),
        len(graph.relations),
    )
    return graph


def update_causal_model(
    graph: CausalGraph,
    *,
    stratum_entities: Iterable[dict[str, Any]] | None = None,
    csie_outputs: dict[str, Any] | Iterable[dict[str, Any]] | None = None,
    workflow_results: Iterable[dict[str, Any]] | None = None,
    cognitive_memory_facts: Iterable[str | dict[str, Any]] | None = None,
) -> CausalGraph:
    update = build_causal_model(
        stratum_entities=stratum_entities,
        csie_outputs=csie_outputs,
        workflow_results=workflow_results,
        cognitive_memory_facts=cognitive_memory_facts,
    )
    for evidence in update.evidence.values():
        graph.add_evidence(evidence)
    for obj in update.objects.values():
        graph.add_object(obj)
    for relation in update.relations.values():
        graph.add_relation(relation)
    logger.info("Updated causal model; graph now has %s objects", len(graph.objects))
    return graph


def export_causal_model(graph: CausalGraph) -> dict[str, Any]:
    return {
        "engine": {
            "mode": "causal_functor_core",
            "version": "core_v1",
            "depends_on": ["stratum", "csie"],
        },
        "causal_graph": graph.to_dict(),
    }


def _ingest_stratum_profile(graph: CausalGraph, profile: dict[str, Any]) -> None:
    stratum_id = str(profile.get("stratum_id") or "").strip()
    identity = profile.get("identity_anchors") or {}
    metadata = profile.get("metadata") or {}
    situational = profile.get("situational_intelligence") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    risk = profile.get("risk_profile") or {}

    identity_value = stratum_id or identity.get("handle") or "unknown"
    identity_obj = graph.add_object(
        create_causal_object(
            "stratum_identity",
            identity_value,
            object_type="entity",
            source="stratum",
            metadata={"stratum_id": stratum_id},
        )
    )
    evidence = _evidence(
        "stratum",
        identity_obj.id,
        f"STRATUM profile {identity_value}",
        profile,
    )

    attributes = [
        ("platform", identity.get("platform"), "observed_in", "context"),
        ("source", metadata.get("source"), "sourced_from", "context"),
        ("country", situational.get("country"), "located_in", "context"),
        ("risk", risk.get("overall_risk"), "has_risk", "state"),
    ]
    for tech in _coerce_list(behavioral.get("tech_stack")):
        attributes.append(("technology", tech, "uses", "capability"))

    for kind, value, relation_type, object_type in attributes:
        if not value:
            continue
        obj = graph.add_object(
            create_causal_object(
                kind,
                str(value),
                object_type=object_type,
                source="stratum",
                metadata={"stratum_id": stratum_id},
            )
        )
        link_objects(
            graph,
            identity_obj.id,
            obj.id,
            relation_type,
            confidence=0.85,
            evidence=evidence,
        )


def _ingest_csie_classification(graph: CausalGraph, classification: dict[str, Any]) -> None:
    stratum_id = str(classification.get("stratum_id") or "unknown")
    csie_obj = graph.add_object(
        create_causal_object(
            "csie_classification",
            stratum_id,
            object_type="diagnostic",
            source="csie",
            metadata={
                "uncertainty_level": classification.get("uncertainty_level"),
                "h1_residual": classification.get("h1_residual"),
            },
        )
    )
    identity_obj = graph.add_object(
        create_causal_object(
            "stratum_identity",
            stratum_id,
            object_type="entity",
            source="stratum",
            metadata={"stratum_id": stratum_id},
        )
    )
    evidence = _evidence(
        "csie",
        csie_obj.id,
        f"CSIE diagnostics for {stratum_id}",
        classification,
        confidence=_csie_confidence(classification),
    )
    link_objects(
        graph,
        identity_obj.id,
        csie_obj.id,
        "explained_by",
        confidence=evidence.confidence,
        evidence=evidence,
    )
    for concept_id in (classification.get("global_section_summary") or {}).get("concept_ids", []):
        concept = graph.add_object(
            create_causal_object(
                "csie_concept",
                str(concept_id),
                object_type="concept",
                source="csie",
            )
        )
        link_objects(
            graph,
            csie_obj.id,
            concept.id,
            "supports",
            confidence=evidence.confidence,
            evidence=evidence,
        )


def _ingest_workflow_result(graph: CausalGraph, result: dict[str, Any]) -> None:
    workflow_id = str(result.get("workflow_id") or result.get("id") or "workflow")
    workflow = graph.add_object(
        create_causal_object(
            "workflow",
            workflow_id,
            object_type="process",
            source="workflow",
            metadata={"status": result.get("status")},
        )
    )
    evidence = _evidence("workflow", workflow.id, f"Workflow result {workflow_id}", result)
    for key, value in result.items():
        if key in {"workflow_id", "id"} or value in (None, "", [], {}):
            continue
        outcome = graph.add_object(
            create_causal_object(
                "workflow_result",
                f"{workflow_id}:{key}",
                object_type="observation",
                source="workflow",
                metadata={"field": key, "value": value},
            )
        )
        link_objects(graph, workflow.id, outcome.id, "produces", confidence=0.8, evidence=evidence)


def _ingest_memory_fact(graph: CausalGraph, fact: str | dict[str, Any]) -> None:
    if isinstance(fact, dict):
        text = str(fact.get("fact") or fact.get("summary") or "").strip()
        confidence = float(fact.get("confidence") or 0.75)
        category = str(fact.get("category") or "memory")
        payload = fact
    else:
        text = str(fact or "").strip()
        confidence = 0.75
        category = "memory"
        payload = {"fact": text}
    if not text:
        return
    obj = graph.add_object(
        create_causal_object(
            "memory_fact",
            text[:80],
            object_type="fact",
            source="memory",
            confidence=confidence,
            metadata={"category": category},
        )
    )
    graph.add_evidence(
        _evidence("memory", obj.id, text, payload, confidence=confidence)
    )


def _iter_csie_classifications(
    csie_outputs: dict[str, Any] | Iterable[dict[str, Any]] | None,
) -> Iterable[dict[str, Any]]:
    if csie_outputs is None:
        return ()
    if isinstance(csie_outputs, dict):
        if "classifications" in csie_outputs:
            return tuple(csie_outputs.get("classifications") or ())
        return (csie_outputs,)
    return tuple(csie_outputs)


def _evidence(
    source_type: str,
    source_id: str,
    description: str,
    payload: dict[str, Any],
    *,
    confidence: float = 0.9,
) -> CausalEvidence:

    return CausalEvidence(
        id=f"ev:{normalize_id_part(source_type)}:{normalize_id_part(source_id)}",
        source_type=source_type,
        source_id=source_id,
        description=description,
        confidence=confidence,
        payload=payload,
    )

def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item).strip()]
    return []


def _csie_confidence(classification: dict[str, Any]) -> float:
    uncertainty = str(classification.get("uncertainty_level") or "").upper()
    if uncertainty == "LOW":
        return 0.9
    if uncertainty == "MEDIUM":
        return 0.65
    if uncertainty == "HIGH":
        return 0.4
    return 0.5
