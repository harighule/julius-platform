"""K-morphism helpers for the Causal Functor core."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .models import CausalGraph, clamp_confidence, require_non_empty


@dataclass(slots=True)
class KMorphism:
    """A finite k-morphism over existing causal objects or relations."""

    id: str
    k: int
    source_id: str
    target_id: str
    relation_type: str
    confidence: float = 1.0
    context_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    evidence_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = require_non_empty(self.id, "KMorphism.id")
        self.k = int(self.k)
        if self.k < 1:
            raise ValueError("KMorphism.k must be >= 1")
        self.source_id = require_non_empty(self.source_id, "KMorphism.source_id")
        self.target_id = require_non_empty(self.target_id, "KMorphism.target_id")
        self.relation_type = require_non_empty(
            self.relation_type, "KMorphism.relation_type"
        )
        self.confidence = clamp_confidence(self.confidence)
        self.context_ids = tuple(
            str(context_id).strip()
            for context_id in self.context_ids
            if str(context_id).strip()
        )
        self.evidence_ids = tuple(
            str(evidence_id).strip()
            for evidence_id in self.evidence_ids
            if str(evidence_id).strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_identity(self) -> bool:
        return (
            self.relation_type == "identity"
            and self.source_id == self.target_id
            and bool(self.metadata.get("identity"))
        )


@dataclass(slots=True)
class IdentityMorphism:
    """Identity morphism id_A for a causal object A."""

    object_id: str

    def as_k_morphism(self) -> KMorphism:
        object_id = require_non_empty(self.object_id, "IdentityMorphism.object_id")
        return KMorphism(
            id=f"id:{object_id}",
            k=1,
            source_id=object_id,
            target_id=object_id,
            relation_type="identity",
            confidence=1.0,
            metadata={"identity": True},
        )


class MorphismComposition:
    """Composition helper for finite k-morphisms."""

    @staticmethod
    def compose(first: KMorphism, second: KMorphism) -> KMorphism:
        MorphismValidation.require_composable(first, second)
        if first.is_identity:
            return second
        if second.is_identity:
            return first
        return KMorphism(
            id=f"comp:{first.id}:{second.id}",
            k=max(first.k, second.k),
            source_id=first.source_id,
            target_id=second.target_id,
            relation_type=f"composed({first.relation_type},{second.relation_type})",
            confidence=first.confidence * second.confidence,
            context_ids=tuple(sorted(set(first.context_ids) | set(second.context_ids))),
            evidence_ids=tuple(sorted(set(first.evidence_ids) | set(second.evidence_ids))),
            metadata={"composed_from": (first.id, second.id)},
        )

    @staticmethod
    def serialize(morphism: KMorphism) -> dict[str, Any]:
        return morphism.to_dict()

    @staticmethod
    def serialize_many(morphisms: list[KMorphism] | tuple[KMorphism, ...]) -> list[dict[str, Any]]:
        return [morphism.to_dict() for morphism in morphisms]


class MorphismValidation:
    """Validation helpers used by tests, diagnostics, and builders."""

    @staticmethod
    def validate_morphism(morphism: KMorphism, graph: CausalGraph | None = None) -> dict[str, Any]:
        errors: list[str] = []
        if morphism.k < 1:
            errors.append("k must be >= 1")
        if not morphism.source_id:
            errors.append("source_id is required")
        if not morphism.target_id:
            errors.append("target_id is required")
        if graph is not None:
            if morphism.source_id not in graph.objects and morphism.source_id not in graph.relations:
                errors.append(f"source_id not found: {morphism.source_id}")
            if morphism.target_id not in graph.objects and morphism.target_id not in graph.relations:
                errors.append(f"target_id not found: {morphism.target_id}")
        return {"valid": not errors, "errors": errors}

    @staticmethod
    def require_composable(first: KMorphism, second: KMorphism) -> None:
        if first.target_id != second.source_id:
            raise ValueError(
                f"Non-composable morphisms: {first.id} target {first.target_id!r} "
                f"does not match {second.id} source {second.source_id!r}"
            )

    @staticmethod
    def validate_graph(graph: CausalGraph) -> dict[str, Any]:
        errors: list[str] = []
        for relation in graph.relations.values():
            if relation.source not in graph.objects:
                errors.append(f"relation {relation.id} has missing source {relation.source}")
            if relation.target not in graph.objects:
                errors.append(f"relation {relation.id} has missing target {relation.target}")
            for evidence_id in relation.evidence_ids:
                if evidence_id not in graph.evidence:
                    errors.append(
                        f"relation {relation.id} references missing evidence {evidence_id}"
                    )
        return {"valid": not errors, "errors": errors}

    @staticmethod
    def diagnostics(
        morphisms: list[KMorphism] | tuple[KMorphism, ...]
    ) -> dict[str, Any]:
        by_k: dict[int, int] = {}

        identities = 0
        confidence_total = 0.0

        for morphism in morphisms:
            by_k[morphism.k] = by_k.get(morphism.k, 0) + 1

            if morphism.is_identity:
                identities += 1

            confidence_total += morphism.confidence

        count = len(morphisms)

        return {
            "morphism_count": count,
            "identity_count": identities,
            "by_k": dict(sorted(by_k.items())),
            "average_confidence": (
                confidence_total / count if count else 0.0
            ),
        }