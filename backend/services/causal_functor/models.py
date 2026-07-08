"""Core data structures for the Causal Functor layer."""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


CausalSourceType = Literal["stratum", "csie", "workflow", "memory", "manual"]
InferenceDirection = Literal["forward", "backward", "chain"]


def require_non_empty(value: str, field_name: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field_name} must be a non-empty string")
    return cleaned


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class CausalObject:
    """A causal variable imported from existing JULIUS sources."""

    id: str
    name: str
    object_type: str
    source: CausalSourceType = "manual"
    confidence: float = 1.0
    context_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = require_non_empty(self.id, "CausalObject.id")
        self.name = require_non_empty(self.name, "CausalObject.name")
        self.object_type = require_non_empty(
            self.object_type, "CausalObject.object_type"
        )
        self.confidence = clamp_confidence(self.confidence)
        self.context_ids = tuple(
            str(context_id).strip()
            for context_id in self.context_ids
            if str(context_id).strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CausalEvidence:
    """Evidence supporting a causal object or relation."""

    id: str
    source_type: CausalSourceType
    source_id: str
    description: str
    confidence: float = 1.0
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = require_non_empty(self.id, "CausalEvidence.id")
        self.source_id = require_non_empty(self.source_id, "CausalEvidence.source_id")
        self.description = str(self.description or "").strip()
        self.confidence = clamp_confidence(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CausalRelation:
    """A directed causal relation between two causal objects."""

    id: str
    source: str
    target: str
    relation_type: str
    confidence: float = 1.0
    evidence_ids: tuple[str, ...] | list[str] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = require_non_empty(self.id, "CausalRelation.id")
        self.source = require_non_empty(self.source, "CausalRelation.source")
        self.target = require_non_empty(self.target, "CausalRelation.target")
        self.relation_type = require_non_empty(
            self.relation_type, "CausalRelation.relation_type"
        )
        self.confidence = clamp_confidence(self.confidence)
        self.evidence_ids = tuple(
            str(evidence_id).strip()
            for evidence_id in self.evidence_ids
            if str(evidence_id).strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class CausalInferenceResult:
    """Serializable result produced by causal inference functions."""

    query: str
    direction: InferenceDirection
    source_id: str
    target_id: str | None
    chains: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    confidence: float = 0.0
    explanation: str = ""
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.query = str(self.query or "").strip()
        self.source_id = require_non_empty(
            self.source_id, "CausalInferenceResult.source_id"
        )
        self.confidence = clamp_confidence(self.confidence)
        self.chains = tuple(tuple(chain) for chain in self.chains)
        self.evidence_ids = tuple(
            str(evidence_id).strip()
            for evidence_id in self.evidence_ids
            if str(evidence_id).strip()
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CausalGraph:
    """In-memory directed graph for causal objects, relations, and evidence."""

    def __init__(self) -> None:
        self.objects: dict[str, CausalObject] = {}
        self.relations: dict[str, CausalRelation] = {}
        self.evidence: dict[str, CausalEvidence] = {}
        self.outgoing: dict[str, list[str]] = {}
        self.incoming: dict[str, list[str]] = {}

    def add_object(self, obj: CausalObject) -> CausalObject:
        existing = self.objects.get(obj.id)
        if existing is not None:
            return existing
        self.objects[obj.id] = obj
        self.outgoing.setdefault(obj.id, [])
        self.incoming.setdefault(obj.id, [])
        return obj

    def add_evidence(self, evidence: CausalEvidence) -> CausalEvidence:
        existing = self.evidence.get(evidence.id)
        if existing is not None:
            return existing
        self.evidence[evidence.id] = evidence
        return evidence

    def add_relation(self, relation: CausalRelation) -> CausalRelation:
        if relation.source not in self.objects:
            raise ValueError(f"Unknown relation source object: {relation.source}")
        if relation.target not in self.objects:
            raise ValueError(f"Unknown relation target object: {relation.target}")
        existing = self.relations.get(relation.id)
        if existing is not None:
            return existing
        self.relations[relation.id] = relation
        self.outgoing.setdefault(relation.source, []).append(relation.id)
        self.incoming.setdefault(relation.target, []).append(relation.id)
        return relation

    def neighbors(self, object_id: str, *, direction: str = "forward") -> list[CausalRelation]:
        if object_id not in self.objects:
            raise ValueError(f"Unknown causal object: {object_id}")
        relation_ids = (
            self.incoming.get(object_id, [])
            if direction == "backward"
            else self.outgoing.get(object_id, [])
        )
        return [self.relations[relation_id] for relation_id in relation_ids]

    def traverse(
        self,
        start_id: str,
        *,
        direction: str = "forward",
        max_depth: int = 3,
    ) -> dict[str, tuple[str, ...]]:
        """Return reachable objects and one relation path to each."""

        if start_id not in self.objects:
            raise ValueError(f"Unknown causal object: {start_id}")
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        visited: dict[str, tuple[str, ...]] = {start_id: ()}
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(start_id, ())])
        while queue:
            current_id, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            relation_ids = (
                self.incoming.get(current_id, [])
                if direction == "backward"
                else self.outgoing.get(current_id, [])
            )
            for relation_id in relation_ids:
                relation = self.relations[relation_id]
                next_id = relation.source if direction == "backward" else relation.target
                if next_id in visited:
                    continue
                next_path = (*path, relation_id)
                visited[next_id] = next_path
                queue.append((next_id, next_path))
        return visited

    def ancestors(self, object_id: str, *, max_depth: int = 5) -> dict[str, tuple[str, ...]]:
        """Return upstream causal objects and paths ending at object_id."""

        reachable = self.traverse(object_id, direction="backward", max_depth=max_depth)
        return {key: value for key, value in reachable.items() if key != object_id}

    def descendants(self, object_id: str, *, max_depth: int = 5) -> dict[str, tuple[str, ...]]:
        """Return downstream causal objects and paths starting at object_id."""

        reachable = self.traverse(object_id, direction="forward", max_depth=max_depth)
        return {key: value for key, value in reachable.items() if key != object_id}

    def detect_cycles(self) -> tuple[tuple[str, ...], ...]:
        """Detect directed object cycles using DFS over relation targets."""

        cycles: list[tuple[str, ...]] = []
        seen_cycles: set[tuple[str, ...]] = set()

        def visit(current_id: str, stack: list[str], active: set[str]) -> None:
            active.add(current_id)
            stack.append(current_id)
            for relation_id in self.outgoing.get(current_id, []):
                target_id = self.relations[relation_id].target
                if target_id in active:
                    start = stack.index(target_id)
                    cycle = tuple(stack[start:] + [target_id])
                    canonical = _canonical_cycle(cycle)
                    if canonical not in seen_cycles:
                        seen_cycles.add(canonical)
                        cycles.append(cycle)
                    continue
                visit(target_id, stack, active)
            stack.pop()
            active.remove(current_id)

        for object_id in self.objects:
            visit(object_id, [], set())
        return tuple(cycles)

    def relation_chain_confidence(self, relation_ids: tuple[str, ...]) -> float:
        confidence = 1.0
        for relation_id in relation_ids:
            relation = self.relations.get(relation_id)
            if relation is None:
                return 0.0
            confidence *= relation.confidence
        return clamp_confidence(confidence)

    def propagate_confidence(self, start_id: str, *, max_depth: int = 3) -> dict[str, float]:
        """Propagate path confidence from a source to reachable descendants."""

        reachable = self.descendants(start_id, max_depth=max_depth)
        return {
            object_id: self.relation_chain_confidence(path)
            for object_id, path in reachable.items()
        }

    def validate(self) -> dict[str, Any]:
        """Validate graph consistency without depending on diagnostics imports."""

        errors: list[str] = []
        for object_id, obj in self.objects.items():
            if object_id != obj.id:
                errors.append(f"object key mismatch: {object_id} != {obj.id}")
        for relation in self.relations.values():
            if relation.source not in self.objects:
                errors.append(f"relation {relation.id} has missing source {relation.source}")
            if relation.target not in self.objects:
                errors.append(f"relation {relation.id} has missing target {relation.target}")
            for evidence_id in relation.evidence_ids:
                if evidence_id not in self.evidence:
                    errors.append(
                        f"relation {relation.id} references missing evidence {evidence_id}"
                    )
        return {
            "valid": not errors,
            "error_count": len(errors),
            "errors": errors,
            "cycle_count": len(self.detect_cycles()),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "objects": [obj.to_dict() for obj in self.objects.values()],
            "relations": [relation.to_dict() for relation in self.relations.values()],
            "evidence": [evidence.to_dict() for evidence in self.evidence.values()],
            "counts": {
                "objects": len(self.objects),
                "relations": len(self.relations),
                "evidence": len(self.evidence),
            },
        }


def _canonical_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    body = cycle[:-1]
    if not body:
        return cycle
    rotations = [body[index:] + body[:index] for index in range(len(body))]
    return min(rotations)
