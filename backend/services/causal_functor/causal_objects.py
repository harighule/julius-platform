"""Causal object creation and linking utilities."""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import CausalEvidence, CausalGraph, CausalObject, CausalRelation

logger = logging.getLogger(__name__)

_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")


def normalize_id_part(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = _ID_SAFE_RE.sub("_", cleaned).strip("_")
    return cleaned or "unknown"


def causal_object_id(kind: str, value: str) -> str:
    return f"{normalize_id_part(kind)}:{normalize_id_part(value)}"


def create_causal_object(
    kind: str,
    value: str,
    *,
    object_type: str = "entity",
    source: str = "manual",
    confidence: float = 1.0,
    context_ids: tuple[str, ...] | list[str] = (),
    metadata: dict[str, Any] | None = None,
) -> CausalObject:
    obj = CausalObject(
        id=causal_object_id(kind, value),
        name=str(value or kind).strip() or "unknown",
        object_type=object_type,
        source=source,  # type: ignore[arg-type]
        confidence=confidence,
        context_ids=context_ids,
        metadata={"kind": kind, "value": value, **(metadata or {})},
    )
    logger.debug("Created causal object %s from %s", obj.id, source)
    return obj


def validate_object(obj: CausalObject) -> bool:
    return bool(obj.id and obj.name and obj.object_type and 0.0 <= obj.confidence <= 1.0)


def link_objects(
    graph: CausalGraph,
    source_id: str,
    target_id: str,
    relation_type: str,
    *,
    confidence: float = 1.0,
    evidence: CausalEvidence | None = None,
    metadata: dict[str, Any] | None = None,
) -> CausalRelation:

    if evidence is not None:
        graph.add_evidence(evidence)

    relation = CausalRelation(
    id=f"r:{normalize_id_part(source_id)}:{normalize_id_part(relation_type)}:{normalize_id_part(target_id)}",
    source=source_id,
    target=target_id,
    relation_type=relation_type,
    confidence=confidence,
    evidence_ids=(evidence.id,) if evidence else (),
    metadata=metadata or {},
)

    stored = graph.add_relation(relation)

    logger.debug(
        "Linked causal relation %s -> %s as %s",
        source_id,
        target_id,
        relation_type,
    )

    return stored