"""Inference helpers for the Causal Functor core."""

from __future__ import annotations

import logging
from collections import deque
from typing import Iterable

from .models import CausalGraph, CausalInferenceResult

logger = logging.getLogger(__name__)


def causal_chain(
    graph: CausalGraph,
    source_id: str,
    target_id: str,
    *,
    max_depth: int = 4,
) -> tuple[tuple[str, ...], ...]:
    """Return relation-id chains from source to target."""

    if source_id not in graph.objects or target_id not in graph.objects:
        return ()
    queue: deque[tuple[str, tuple[str, ...], set[str]]] = deque(
        [(source_id, (), {source_id})]
    )
    chains: list[tuple[str, ...]] = []
    while queue:
        current_id, relation_path, seen = queue.popleft()
        if len(relation_path) >= max_depth:
            continue
        for relation_id in graph.outgoing.get(current_id, []):
            relation = graph.relations[relation_id]
            next_path = (*relation_path, relation_id)
            if relation.target == target_id:
                chains.append(next_path)
                continue
            if relation.target in seen:
                continue
            queue.append((relation.target, next_path, {*seen, relation.target}))
    logger.debug("Found %s causal chains from %s to %s", len(chains), source_id, target_id)
    return tuple(chains)


def forward_inference(
    graph: CausalGraph,
    source_id: str,
    *,
    max_depth: int = 3,
) -> CausalInferenceResult:
    """Infer downstream effects reachable from a causal source."""

    chains = _walk(graph, source_id, direction="forward", max_depth=max_depth)
    confidence = _average_chain_confidence(graph, chains)
    result = CausalInferenceResult(
        query=f"forward:{source_id}",
        direction="forward",
        source_id=source_id,
        target_id=None,
        chains=chains,
        confidence=confidence,
        evidence_ids=_evidence_for_chains(graph, chains),
        metadata={"reachable_count": len(chains)},
    )
    result.explanation = explanation_generation(result, graph)
    return result


def backward_inference(
    graph: CausalGraph,
    target_id: str,
    *,
    max_depth: int = 3,
) -> CausalInferenceResult:
    """Infer upstream causes that can reach a target."""

    chains = _walk(graph, target_id, direction="backward", max_depth=max_depth)
    confidence = _average_chain_confidence(graph, chains)
    result = CausalInferenceResult(
        query=f"backward:{target_id}",
        direction="backward",
        source_id=target_id,
        target_id=target_id,
        chains=chains,
        confidence=confidence,
        evidence_ids=_evidence_for_chains(graph, chains),
        metadata={"reachable_count": len(chains)},
    )
    result.explanation = explanation_generation(result, graph)
    return result


def explanation_generation(
    result: CausalInferenceResult,
    graph: CausalGraph,
) -> str:
    """Generate a deterministic explanation from relation chains."""

    if not result.chains:
        return "No causal chain was found for the query."
    descriptions: list[str] = []
    for chain in result.chains[:3]:
        parts: list[str] = []
        for relation_id in chain:
            relation = graph.relations.get(relation_id)
            if relation is None:
                continue
            source = graph.objects[relation.source].name
            target = graph.objects[relation.target].name
            parts.append(f"{source} {relation.relation_type} {target}")
        if parts:
            descriptions.append(" -> ".join(parts))
    return "Causal explanation: " + "; ".join(descriptions)


def _walk(
    graph: CausalGraph,
    start_id: str,
    *,
    direction: str,
    max_depth: int,
) -> tuple[tuple[str, ...], ...]:
    if start_id not in graph.objects:
        return ()
    queue: deque[tuple[str, tuple[str, ...], set[str]]] = deque(
        [(start_id, (), {start_id})]
    )
    chains: list[tuple[str, ...]] = []
    while queue:
        current_id, relation_path, seen = queue.popleft()
        if len(relation_path) >= max_depth:
            continue
        relation_ids = (
            graph.incoming.get(current_id, [])
            if direction == "backward"
            else graph.outgoing.get(current_id, [])
        )
        for relation_id in relation_ids:
            relation = graph.relations[relation_id]
            next_object_id = relation.source if direction == "backward" else relation.target
            next_path = (*relation_path, relation_id)
            chains.append(next_path)
            if next_object_id in seen:
                continue
            queue.append((next_object_id, next_path, {*seen, next_object_id}))
    return tuple(chains)


def _average_chain_confidence(
    graph: CausalGraph,
    chains: Iterable[tuple[str, ...]],
) -> float:
    chain_values = [
        graph.relation_chain_confidence(chain)
        for chain in chains
    ]

    if not chain_values:
        return 0.0

    return sum(chain_values) / len(chain_values)


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
