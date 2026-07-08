"""Core CSIE data structures.

These types are intentionally dependency-light for the MVP. Later phases can
attach NumPy/PyTorch vectors at the boundary, but the graph and sheaf records
should remain safe to serialize and test with only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


RELATION_TYPES: tuple[str, ...] = (
    "causes",
    "is_a",
    "has_property",
    "precedes",
    "enables",
    "prevents",
    "requires",
    "produces",
    "consumes",
    "part_of",
    "instance_of",
    "related_to",
    "used_for",
    "at_location",
    "context_split",
)


def _require_non_empty(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string")
    return cleaned


def _coerce_vector(values: tuple[float, ...] | list[float] | None) -> tuple[float, ...]:
    if values is None:
        return ()
    return tuple(float(v) for v in values)


@dataclass(slots=True)
class SemanticObject:
    """A category object representing a concept, entity, event, or property."""

    id: str
    type_signature: str
    prototype_vector: tuple[float, ...] | list[float] | None = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _require_non_empty(self.id, "SemanticObject.id")
        self.type_signature = _require_non_empty(
            self.type_signature, "SemanticObject.type_signature"
        )
        self.prototype_vector = _coerce_vector(self.prototype_vector)


@dataclass(slots=True)
class Morphism:
    """A typed semantic relation between two category objects."""

    id: str
    source: str
    target: str
    relation_type: str
    weight: float
    context_restriction: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _require_non_empty(self.id, "Morphism.id")
        self.source = _require_non_empty(self.source, "Morphism.source")
        self.target = _require_non_empty(self.target, "Morphism.target")
        self.relation_type = _require_non_empty(
            self.relation_type, "Morphism.relation_type"
        )
        if self.relation_type not in RELATION_TYPES and not self.relation_type.startswith(
            "composed("
        ):
            raise ValueError(f"Unsupported relation_type: {self.relation_type}")
        self.weight = max(0.0, min(1.0, float(self.weight)))
        self.context_restriction = tuple(
            str(ctx).strip()
            for ctx in self.context_restriction
            if str(ctx).strip()
        )


@dataclass(slots=True)
class SemanticSection:
    """A local interpretation of a concept inside one or more contexts."""

    concept_id: str
    interpretation: tuple[float, ...] | list[float]
    confidence: float
    source_contexts: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.concept_id = _require_non_empty(self.concept_id, "SemanticSection.concept_id")
        self.interpretation = _coerce_vector(self.interpretation)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_contexts = tuple(
            str(ctx).strip()
            for ctx in self.source_contexts
            if str(ctx).strip()
        )


@dataclass(slots=True)
class ContextNode:
    """A context neighborhood that can hold local semantic sections."""

    id: str
    description: str
    parent_contexts: tuple[str, ...] | list[str] = field(default_factory=tuple)
    child_contexts: tuple[str, ...] | list[str] = field(default_factory=tuple)
    sections: dict[str, SemanticSection] = field(default_factory=dict)
    activation_signature: tuple[float, ...] | list[float] | None = field(
        default_factory=tuple
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _require_non_empty(self.id, "ContextNode.id")
        self.description = str(self.description or "").strip()
        self.parent_contexts = tuple(
            str(ctx).strip()
            for ctx in self.parent_contexts
            if str(ctx).strip()
        )
        self.child_contexts = tuple(
            str(ctx).strip()
            for ctx in self.child_contexts
            if str(ctx).strip()
        )
        self.activation_signature = _coerce_vector(self.activation_signature)

