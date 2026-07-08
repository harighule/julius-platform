"""CSIE category engine for semantic objects and morphisms."""

from __future__ import annotations

import re
from collections import deque
from typing import Any

from .csie_types import Morphism, SemanticObject


_ID_SAFE_RE = re.compile(r"[^a-z0-9]+")


def deterministic_object_id(kind: str, value: str) -> str:
    """Return a stable CSIE object id for a source-domain value."""

    kind_part = _normalize_id_part(kind)
    value_part = _normalize_id_part(value)
    if not value_part:
        value_part = "unknown"
    return f"{kind_part}:{value_part}"


def platform_object_id(platform: str) -> str:
    return deterministic_object_id("platform", platform)


def source_object_id(source: str) -> str:
    return deterministic_object_id("source", source)


def country_object_id(country: str) -> str:
    return deterministic_object_id("country", country)


def tech_stack_object_id(technology: str) -> str:
    return deterministic_object_id("tech", technology)


def risk_object_id(risk_level: str) -> str:
    return deterministic_object_id("risk", risk_level)


def make_semantic_object(
    kind: str,
    value: str,
    *,
    type_signature: str = "concept",
    prototype_vector: tuple[float, ...] | list[float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> SemanticObject:
    """Build a `SemanticObject` with a deterministic id."""

    return SemanticObject(
        id=deterministic_object_id(kind, value),
        type_signature=type_signature,
        prototype_vector=prototype_vector,
        metadata={"kind": kind, "value": value, **(metadata or {})},
    )


class Category:
    """Directed multigraph of semantic objects and typed morphisms."""

    def __init__(self) -> None:
        self.objects: dict[str, SemanticObject] = {}
        self.morphisms: dict[str, Morphism] = {}
        self.hom_index: dict[tuple[str, str], list[str]] = {}
        self.outgoing: dict[str, list[str]] = {}
        self.incoming: dict[str, list[str]] = {}

    def add_object(self, obj: SemanticObject) -> SemanticObject:
        """Add an object idempotently and return the stored object."""

        existing = self.objects.get(obj.id)
        if existing is not None:
            return existing
        self.objects[obj.id] = obj
        self.outgoing.setdefault(obj.id, [])
        self.incoming.setdefault(obj.id, [])
        return obj

    def add_morphism(self, morphism: Morphism) -> Morphism:
        """Add a morphism and update all graph indexes."""

        if morphism.source not in self.objects:
            raise ValueError(f"Unknown morphism source object: {morphism.source}")
        if morphism.target not in self.objects:
            raise ValueError(f"Unknown morphism target object: {morphism.target}")

        existing = self.morphisms.get(morphism.id)
        if existing is not None:
            if existing != morphism:
                raise ValueError(f"Conflicting morphism id already exists: {morphism.id}")
            return existing

        self.morphisms[morphism.id] = morphism
        key = (morphism.source, morphism.target)
        self.hom_index.setdefault(key, []).append(morphism.id)
        self.outgoing.setdefault(morphism.source, []).append(morphism.id)
        self.incoming.setdefault(morphism.target, []).append(morphism.id)
        return morphism

    def compose(
        self,
        f_id: str,
        g_id: str,
        *,
        morphism_id: str | None = None,
        relation_type: str | None = None,
        add: bool = True,
    ) -> Morphism:
        """Compose f: A -> B and g: B -> C into g o f: A -> C."""

        f = self._require_morphism(f_id)
        g = self._require_morphism(g_id)
        if f.target != g.source:
            raise ValueError(
                f"Non-composable morphisms: {f.id} target {f.target!r} "
                f"does not match {g.id} source {g.source!r}"
            )

        composed = Morphism(
            id=morphism_id or f"comp:{f.id}:{g.id}",
            source=f.source,
            target=g.target,
            relation_type=relation_type
            or f"composed({f.relation_type},{g.relation_type})",
            weight=f.weight * g.weight,
            context_restriction=tuple(
                sorted(set(f.context_restriction) | set(g.context_restriction))
            ),
            metadata={"composed_from": (f.id, g.id)},
        )
        if add:
            return self.add_morphism(composed)
        return composed

    def hom(self, source: str, target: str) -> list[Morphism]:
        """Return all morphisms from source to target."""

        return [
            self.morphisms[morphism_id]
            for morphism_id in self.hom_index.get((source, target), [])
        ]

    def reachable(self, source_id: str, max_depth: int = 3) -> dict[str, list[str]]:
        """Return targets reachable from `source_id` and one path to each."""

        if source_id not in self.objects:
            raise ValueError(f"Unknown source object: {source_id}")
        if max_depth < 0:
            raise ValueError("max_depth must be >= 0")

        visited: dict[str, list[str]] = {source_id: []}
        queue: deque[tuple[str, list[str]]] = deque([(source_id, [])])

        while queue:
            current, path = queue.popleft()
            if len(path) >= max_depth:
                continue
            for morphism_id in self.outgoing.get(current, []):
                morphism = self.morphisms[morphism_id]
                if morphism.target in visited:
                    continue
                next_path = [*path, morphism_id]
                visited[morphism.target] = next_path
                queue.append((morphism.target, next_path))

        return visited

    def _require_morphism(self, morphism_id: str) -> Morphism:
        morphism = self.morphisms.get(morphism_id)
        if morphism is None:
            raise ValueError(f"Unknown morphism id: {morphism_id}")
        return morphism


def _normalize_id_part(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = _ID_SAFE_RE.sub("_", cleaned).strip("_")
    return cleaned

