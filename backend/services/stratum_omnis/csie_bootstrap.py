"""Profile-to-CSIE conversion helpers for STRATUM profile dictionaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .csie_category import Category, deterministic_object_id, make_semantic_object
from .csie_sheaf import SheafStore, context_id, deterministic_vector, mean_vector
from .csie_types import ContextNode, Morphism, SemanticSection


@dataclass(frozen=True, slots=True)
class ProfileConversionResult:
    stratum_id: str
    identity_object_id: str
    context_ids: tuple[str, ...]
    morphism_ids: tuple[str, ...]
    section_ids: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class CSIEBootstrapResult:
    category: Category
    sheaf: SheafStore
    conversions: tuple[ProfileConversionResult, ...]


def build_csie_from_profiles(
    profiles: Iterable[dict[str, Any]],
    *,
    embedding_dim: int = 512,
) -> CSIEBootstrapResult:
    category = Category()
    sheaf = SheafStore(embedding_dim=embedding_dim)
    conversions = [
        convert_profile_to_csie(profile, category, sheaf)
        for profile in profiles
    ]
    return CSIEBootstrapResult(
        category=category,
        sheaf=sheaf,
        conversions=tuple(conversions),
    )


def convert_profile_to_csie(
    profile: dict[str, Any],
    category: Category,
    sheaf: SheafStore,
) -> ProfileConversionResult:
    identity = profile.get("identity_anchors") or {}
    metadata = profile.get("metadata") or {}
    situational = profile.get("situational_intelligence") or {}
    behavioral = profile.get("behavioral_intelligence") or {}
    risk = profile.get("risk_profile") or {}

    stratum_id = _clean(profile.get("stratum_id")) or _clean(identity.get("handle")) or "unknown"
    identity_object = category.add_object(
        make_semantic_object(
            "identity",
            stratum_id,
            type_signature="entity",
            prototype_vector=deterministic_vector(f"identity:{stratum_id}", sheaf.embedding_dim),
            metadata={"stratum_id": stratum_id},
        )
    )

    context_ids: list[str] = []
    morphism_ids: list[str] = []
    section_ids: list[tuple[str, str]] = []

    root_ctx_id = _ensure_context(
        sheaf,
        kind="root",
        value="global",
        description="Global CSIE context",
        parents=[],
        labels=["root:global"],
    )
    context_ids.append(root_ctx_id)

    targets: list[tuple[str, str, str, str, str]] = []
    platform = _clean(identity.get("platform"))
    source = _clean(metadata.get("source"))
    country = _clean(situational.get("country"))
    risk_level = _clean(risk.get("overall_risk"))
    tech_stack = _coerce_list(behavioral.get("tech_stack"))

    if platform:
        targets.append(("platform", platform, "is_a", "concept", root_ctx_id))
    if source:
        targets.append(("source", source, "related_to", "concept", root_ctx_id))
    if country:
        targets.append(("country", country, "at_location", "property", root_ctx_id))
    if risk_level:
        targets.append(("risk", risk_level, "has_property", "property", root_ctx_id))
    for technology in tech_stack:
        targets.append(("tech", technology, "used_for", "property", root_ctx_id))

    for kind, value, relation_type, type_signature, parent_ctx_id in targets:
        object_id = deterministic_object_id(kind, value)
        category.add_object(
            make_semantic_object(
                kind,
                value,
                type_signature=type_signature,
                prototype_vector=deterministic_vector(object_id, sheaf.embedding_dim),
            )
        )
        ctx_id = _ensure_context(
            sheaf,
            kind=kind,
            value=value,
            description=f"{kind} context: {value}",
            parents=[parent_ctx_id],
            labels=[object_id, f"{kind}:{value}"],
        )
        if ctx_id not in context_ids:
            context_ids.append(ctx_id)

        morphism_id = f"m:{identity_object.id}:{object_id}:{relation_type}"
        morphism = category.add_morphism(
            Morphism(
                id=morphism_id,
                source=identity_object.id,
                target=object_id,
                relation_type=relation_type,
                weight=1.0,
                context_restriction=[ctx_id],
                metadata={"stratum_id": stratum_id},
            )
        )
        if morphism.id not in morphism_ids:
            morphism_ids.append(morphism.id)

        for concept_id, label in [
            (identity_object.id, f"{identity_object.id}@{ctx_id}"),
            (object_id, f"{object_id}@{ctx_id}"),
        ]:
            section = SemanticSection(
                concept_id=concept_id,
                interpretation=deterministic_vector(label, sheaf.embedding_dim),
                confidence=1.0,
                source_contexts=[ctx_id],
                metadata={"stratum_id": stratum_id},
            )
            sheaf.add_section(ctx_id, concept_id, section)
            section_key = (ctx_id, concept_id)
            if section_key not in section_ids:
                section_ids.append(section_key)

    return ProfileConversionResult(
        stratum_id=stratum_id,
        identity_object_id=identity_object.id,
        context_ids=tuple(context_ids),
        morphism_ids=tuple(morphism_ids),
        section_ids=tuple(section_ids),
    )


def _ensure_context(
    sheaf: SheafStore,
    *,
    kind: str,
    value: str,
    description: str,
    parents: list[str],
    labels: list[str],
) -> str:
    ctx_id = context_id(kind, value)
    if ctx_id in sheaf.contexts:
        return ctx_id
    signature = mean_vector(
        [deterministic_vector(label, sheaf.embedding_dim) for label in labels],
        sheaf.embedding_dim,
    )
    sheaf.add_context(
        ContextNode(
            id=ctx_id,
            description=description,
            parent_contexts=parents,
            child_contexts=[],
            sections={},
            activation_signature=signature,
            metadata={"kind": kind, "value": value},
        )
    )
    return ctx_id


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_clean(value)] if _clean(value) else []
    if isinstance(value, Iterable):
        result: list[str] = []
        for item in value:
            cleaned = _clean(item)
            if cleaned:
                result.append(cleaned)
        return result
    return []

