"""CSIE sheaf-memory stores and vector utilities.

Day 2 keeps this layer dependency-light. The implementation uses deterministic
hash vectors and pure-Python cosine search so it remains safe in the current
backend environment without NumPy/SciPy.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Iterable

from .csie_types import ContextNode, SemanticSection


DEFAULT_EMBEDDING_DIM = 512
_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class GluingValidation:
    """Result of checking whether shared sections agree on an overlap."""

    context_a: str
    context_b: str
    threshold: float
    similarities: dict[str, float]
    violations: dict[str, float]

    @property
    def passed(self) -> bool:
        return not self.violations


class ContextStore:
    """In-memory store for CSIE context nodes."""

    def __init__(self) -> None:
        self.contexts: dict[str, ContextNode] = {}

    def add(self, ctx: ContextNode) -> ContextNode:
        existing = self.contexts.get(ctx.id)
        if existing is not None:
            return existing
        self.contexts[ctx.id] = ctx
        return ctx

    def get(self, ctx_id: str) -> ContextNode | None:
        return self.contexts.get(ctx_id)

    def require(self, ctx_id: str) -> ContextNode:
        ctx = self.get(ctx_id)
        if ctx is None:
            raise ValueError(f"Unknown context id: {ctx_id}")
        return ctx

    def all(self) -> list[ContextNode]:
        return list(self.contexts.values())


class SectionStore:
    """Section operations scoped to a `ContextStore`."""

    def __init__(self, context_store: ContextStore) -> None:
        self.context_store = context_store

    def add(self, ctx_id: str, concept_id: str, section: SemanticSection) -> SemanticSection:
        if section.concept_id != concept_id:
            raise ValueError(
                f"Section concept_id {section.concept_id!r} does not match {concept_id!r}"
            )
        ctx = self.context_store.require(ctx_id)
        ctx.sections[concept_id] = section
        return section

    def get(self, ctx_id: str, concept_id: str) -> SemanticSection | None:
        return self.sections(ctx_id).get(concept_id)

    def sections(self, ctx_id: str) -> dict[str, SemanticSection]:
        ctx = self.context_store.get(ctx_id)
        if ctx is None:
            return {}
        return ctx.sections

    def shared_concepts(self, a_id: str, b_id: str) -> set[str]:
        return set(self.sections(a_id)) & set(self.sections(b_id))


class SheafStore:
    """Persistent-memory shaped store for context neighborhoods and sections."""

    def __init__(self, embedding_dim: int = DEFAULT_EMBEDDING_DIM) -> None:
        if embedding_dim <= 0:
            raise ValueError("embedding_dim must be > 0")
        self.embedding_dim = embedding_dim
        self.context_store = ContextStore()
        self.section_store = SectionStore(self.context_store)
        self._ids: list[str] = []
        self._matrix: list[tuple[float, ...]] = []

    @property
    def contexts(self) -> dict[str, ContextNode]:
        return self.context_store.contexts

    def add_context(self, ctx: ContextNode) -> ContextNode:
        stored = self.context_store.add(ctx)
        self._link_parent_child(stored)
        self._rebuild_index()
        return stored

    def _rebuild_index(self) -> None:
        self._ids = []
        self._matrix = []
        for ctx_id in sorted(self.contexts):
            ctx = self.contexts[ctx_id]
            vector = _ensure_dimension(ctx.activation_signature, self.embedding_dim)
            if not any(vector):
                vector = deterministic_vector(ctx_id, self.embedding_dim)
                ctx.activation_signature = vector
            self._ids.append(ctx_id)
            self._matrix.append(normalize_vector(vector))

    def find_nearest(self, qv: Iterable[float], k: int = 5) -> list[str]:
        if k <= 0 or not self._ids:
            return []
        query = normalize_vector(_ensure_dimension(tuple(qv), self.embedding_dim))
        scored = [
            (cosine_similarity(query, vector), ctx_id)
            for ctx_id, vector in zip(self._ids, self._matrix)
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [ctx_id for _, ctx_id in scored[:k]]

    def get_covering(self, ctx_ids: Iterable[str]) -> list[str]:
        covering: list[str] = []
        seen: set[str] = set()

        def add_once(ctx_id: str) -> None:
            if ctx_id in self.contexts and ctx_id not in seen:
                seen.add(ctx_id)
                covering.append(ctx_id)

        for raw_id in ctx_ids:
            ctx_id = str(raw_id or "").strip()
            if not ctx_id:
                continue
            add_once(ctx_id)
            ctx = self.contexts.get(ctx_id)
            if ctx is None:
                continue
            for parent_id in ctx.parent_contexts:
                add_once(parent_id)

        return covering

    def sections(self, ctx_id: str) -> dict[str, SemanticSection]:
        return self.section_store.sections(ctx_id)

    def add_section(
        self, ctx_id: str, concept_id: str, section: SemanticSection
    ) -> SemanticSection:
        return self.section_store.add(ctx_id, concept_id, section)

    def check_gluing(self, a_id: str, b_id: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for concept_id in sorted(self.section_store.shared_concepts(a_id, b_id)):
            a_section = self.section_store.get(a_id, concept_id)
            b_section = self.section_store.get(b_id, concept_id)
            if a_section is None or b_section is None:
                continue
            result[concept_id] = cosine_similarity(
                a_section.interpretation, b_section.interpretation
            )
        return result

    def validate_gluing(
        self, a_id: str, b_id: str, threshold: float = 0.70
    ) -> GluingValidation:
        similarities = self.check_gluing(a_id, b_id)
        violations = {
            concept_id: score
            for concept_id, score in similarities.items()
            if score < threshold
        }
        return GluingValidation(
            context_a=a_id,
            context_b=b_id,
            threshold=threshold,
            similarities=similarities,
            violations=violations,
        )

    def _link_parent_child(self, ctx: ContextNode) -> None:
        for parent_id in ctx.parent_contexts:
            parent = self.contexts.get(parent_id)
            if parent is None or ctx.id in parent.child_contexts:
                continue
            parent.child_contexts = tuple([*parent.child_contexts, ctx.id])


def context_id(kind: str, value: str) -> str:
    kind_part = _normalize_id_part(kind) or "context"
    value_part = _normalize_id_part(value) or "unknown"
    return f"ctx:{kind_part}:{value_part}"


def deterministic_vector(
    label: str, dimensions: int = DEFAULT_EMBEDDING_DIM
) -> tuple[float, ...]:
    if dimensions <= 0:
        raise ValueError("dimensions must be > 0")
    values: list[float] = []
    counter = 0
    seed = str(label or "unknown").encode("utf-8")
    while len(values) < dimensions:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dimensions:
                break
        counter += 1
    return normalize_vector(values)


def mean_vector(
    vectors: Iterable[Iterable[float]], dimensions: int = DEFAULT_EMBEDDING_DIM
) -> tuple[float, ...]:
    prepared = [_ensure_dimension(tuple(vector), dimensions) for vector in vectors]
    if not prepared:
        return deterministic_vector("empty:mean", dimensions)
    accum = [0.0] * dimensions
    for vector in prepared:
        for idx, value in enumerate(vector):
            accum[idx] += value
    return normalize_vector(value / len(prepared) for value in accum)


def normalize_vector(values: Iterable[float]) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return tuple(0.0 for _ in vector)
    return tuple(value / norm for value in vector)


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    av = tuple(float(value) for value in a)
    bv = tuple(float(value) for value in b)
    if not av or not bv or len(av) != len(bv):
        return 0.0
    an = math.sqrt(sum(value * value for value in av))
    bn = math.sqrt(sum(value * value for value in bv))
    if an == 0 or bn == 0:
        return 0.0
    score = sum(x * y for x, y in zip(av, bv)) / (an * bn)
    return max(-1.0, min(1.0, score))


def _ensure_dimension(values: Iterable[float], dimensions: int) -> tuple[float, ...]:
    vector = tuple(float(value) for value in values)
    if len(vector) == dimensions:
        return vector
    if len(vector) > dimensions:
        return vector[:dimensions]
    return tuple([*vector, *([0.0] * (dimensions - len(vector)))])


def _normalize_id_part(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    return _ID_SAFE_RE.sub("_", cleaned).strip("_")

