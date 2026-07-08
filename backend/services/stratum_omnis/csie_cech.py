"""Čech-style cohomology solver for the CSIE MVP.

This module intentionally works with the Day 2 `SheafStore` primitives and
does not require SciPy. It models H0 as globally glueable sections and H1 as
unresolved failed gluing across context overlaps.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations
from typing import Iterable, Literal

from .csie_sheaf import SheafStore, cosine_similarity, mean_vector
from .csie_types import SemanticSection


UncertaintyLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True, slots=True)
class CoverOverlap:
    source_context: str
    target_context: str
    shared_concepts: tuple[str, ...]
    similarities: dict[str, float]
    failed_concepts: tuple[str, ...]

    @property
    def has_failure(self) -> bool:
        return bool(self.failed_concepts)


@dataclass(frozen=True, slots=True)
class CechConflict:
    concept_id: str
    source_context: str
    target_context: str
    similarity: float
    threshold: float
    reason: str
    source_value: tuple[float, ...]
    target_value: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeGap:
    concept_id: str
    context_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class PolysemyCandidate:
    concept_id: str
    contexts: tuple[str, ...]
    min_similarity: float
    reason: str


@dataclass(frozen=True, slots=True)
class GlobalSection:
    concept_id: str
    interpretation: tuple[float, ...]
    source_contexts: tuple[str, ...]
    confidence: float


@dataclass(frozen=True, slots=True)
class H1Result:
    residual: float
    conflicts: tuple[CechConflict, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticsOutput:
    global_section_count: int
    conflict_count: int
    knowledge_gap_count: int
    polysemy_count: int
    uncertainty: UncertaintyLevel


@dataclass(frozen=True, slots=True)
class CechSolveResult:
    global_sections: tuple[GlobalSection, ...]
    failed_gluings: tuple[CoverOverlap, ...]
    conflicts: tuple[CechConflict, ...]
    knowledge_gaps: tuple[KnowledgeGap, ...]
    polysemy_candidates: tuple[PolysemyCandidate, ...]
    uncertainty: UncertaintyLevel
    diagnostics: DiagnosticsOutput
    h1_residual: float = 0.0

    def to_dict(self) -> dict:
        return {
            "global_sections": [asdict(section) for section in self.global_sections],
            "failed_gluings": [asdict(overlap) for overlap in self.failed_gluings],
            "conflicts": [asdict(conflict) for conflict in self.conflicts],
            "knowledge_gaps": [asdict(gap) for gap in self.knowledge_gaps],
            "polysemy_candidates": [
                asdict(candidate) for candidate in self.polysemy_candidates
            ],
            "uncertainty": self.uncertainty,
            "diagnostics": asdict(self.diagnostics),
            "h1_residual": self.h1_residual,
        }


@dataclass(slots=True)
class CechDiagnostics:
    gluing_threshold: float = 0.70

    def detect_polysemy(
        self,
        sheaf: SheafStore,
        covering: Iterable[str],
        concept_ids: Iterable[str],
    ) -> tuple[PolysemyCandidate, ...]:
        candidates: list[PolysemyCandidate] = []
        for concept_id in sorted(set(concept_ids)):
            sections = _sections_for_concept(sheaf, covering, concept_id)
            if len(sections) < 2:
                continue
            min_similarity = 1.0
            for (ctx_a, section_a), (ctx_b, section_b) in combinations(
                sections.items(), 2
            ):
                score = cosine_similarity(
                    section_a.interpretation, section_b.interpretation
                )
                min_similarity = min(min_similarity, score)
            if min_similarity < self.gluing_threshold:
                candidates.append(
                    PolysemyCandidate(
                        concept_id=concept_id,
                        contexts=tuple(sorted(sections)),
                        min_similarity=min_similarity,
                        reason="Identical concept id has divergent interpretations across contexts.",
                    )
                )
        return tuple(candidates)

    def detect_knowledge_gaps(
        self,
        sheaf: SheafStore,
        covering: Iterable[str],
        concept_ids: Iterable[str],
    ) -> tuple[KnowledgeGap, ...]:
        gaps: list[KnowledgeGap] = []
        existing_contexts = set(sheaf.contexts)
        for ctx_id in covering:
            if ctx_id not in existing_contexts:
                for concept_id in concept_ids:
                    gaps.append(
                        KnowledgeGap(
                            concept_id=concept_id,
                            context_id=ctx_id,
                            reason="Required context is not present in the sheaf store.",
                        )
                    )
                continue
            sections = sheaf.sections(ctx_id)
            for concept_id in concept_ids:
                if concept_id not in sections:
                    gaps.append(
                        KnowledgeGap(
                            concept_id=concept_id,
                            context_id=ctx_id,
                            reason="Required context has no section for this concept.",
                        )
                    )
        return tuple(gaps)

    def classify_uncertainty(
        self,
        conflicts: Iterable[CechConflict],
        knowledge_gaps: Iterable[KnowledgeGap],
        h1_residual: float = 0.0,
    ) -> UncertaintyLevel:
        conflict_count = len(tuple(conflicts))
        gap_count = len(tuple(knowledge_gaps))
        if conflict_count == 0 and gap_count == 0 and h1_residual <= 0:
            return "LOW"
        if conflict_count >= 4 or gap_count >= 4 or h1_residual > 0:
            return "HIGH"
        return "MEDIUM"

    def summarize_conflicts(
        self, conflicts: Iterable[CechConflict]
    ) -> list[dict[str, object]]:
        return [
            {
                "concept_id": conflict.concept_id,
                "source_context": conflict.source_context,
                "target_context": conflict.target_context,
                "similarity": conflict.similarity,
                "reason": conflict.reason,
            }
            for conflict in conflicts
        ]


class CechSolver:
    """Compute H0/H1-style CSIE diagnostics over a `SheafStore` covering."""

    def __init__(
        self,
        sheaf: SheafStore,
        *,
        gluing_threshold: float = 0.70,
    ) -> None:
        self.sheaf = sheaf
        self.gluing_threshold = gluing_threshold
        self.diagnostics = CechDiagnostics(gluing_threshold=gluing_threshold)

    def compute_cover_overlaps(
        self,
        covering: Iterable[str],
        concept_ids: Iterable[str] | None = None,
    ) -> tuple[CoverOverlap, ...]:
        cover = _stable_covering(covering)
        required = set(concept_ids or [])
        overlaps: list[CoverOverlap] = []
        for source_context, target_context in combinations(cover, 2):
            source_sections = self.sheaf.sections(source_context)
            target_sections = self.sheaf.sections(target_context)
            shared = set(source_sections) & set(target_sections)
            if required:
                shared &= required
            similarities: dict[str, float] = {}
            failed: list[str] = []
            for concept_id in sorted(shared):
                score = cosine_similarity(
                    source_sections[concept_id].interpretation,
                    target_sections[concept_id].interpretation,
                )
                similarities[concept_id] = score
                if score < self.gluing_threshold:
                    failed.append(concept_id)
            if shared or required:
                overlaps.append(
                    CoverOverlap(
                        source_context=source_context,
                        target_context=target_context,
                        shared_concepts=tuple(sorted(shared)),
                        similarities=similarities,
                        failed_concepts=tuple(failed),
                    )
                )
        return tuple(overlaps)

    def compute_h0(
        self,
        covering: Iterable[str],
        concept_ids: Iterable[str] | None = None,
    ) -> tuple[GlobalSection, ...]:
        cover = _stable_covering(covering)
        concepts = self._resolve_concepts(cover, concept_ids)
        conflicts = self.compute_h1(cover, concepts).conflicts
        conflict_concepts = {conflict.concept_id for conflict in conflicts}
        gaps = self.diagnostics.detect_knowledge_gaps(self.sheaf, cover, concepts)
        gap_concepts = {gap.concept_id for gap in gaps}

        global_sections: list[GlobalSection] = []
        for concept_id in concepts:
            if concept_id in conflict_concepts or concept_id in gap_concepts:
                continue
            sections = _sections_for_concept(self.sheaf, cover, concept_id)
            if not sections:
                continue
            vectors = [section.interpretation for section in sections.values()]
            confidence = sum(section.confidence for section in sections.values()) / len(
                sections
            )
            global_sections.append(
                GlobalSection(
                    concept_id=concept_id,
                    interpretation=mean_vector(vectors, self.sheaf.embedding_dim),
                    source_contexts=tuple(sorted(sections)),
                    confidence=confidence,
                )
            )
        return tuple(global_sections)

    def compute_h1(
        self,
        covering: Iterable[str],
        concept_ids: Iterable[str] | None = None,
    ) -> H1Result:
        conflicts: list[CechConflict] = []
        for overlap in self.compute_cover_overlaps(covering, concept_ids):
            for concept_id in overlap.failed_concepts:
                source_section = self.sheaf.section_store.get(
                    overlap.source_context, concept_id
                )
                target_section = self.sheaf.section_store.get(
                    overlap.target_context, concept_id
                )
                if source_section is None or target_section is None:
                    continue
                similarity = overlap.similarities[concept_id]
                conflicts.append(
                    CechConflict(
                        concept_id=concept_id,
                        source_context=overlap.source_context,
                        target_context=overlap.target_context,
                        similarity=similarity,
                        threshold=self.gluing_threshold,
                        reason="Overlap exists but gluing failed; contradiction remains unresolved.",
                        source_value=source_section.interpretation,
                        target_value=target_section.interpretation,
                    )
                )
        residual = _h1_residual(conflicts, self.gluing_threshold)
        return H1Result(residual=residual, conflicts=tuple(conflicts))

    def validate_global_consistency(
        self,
        covering: Iterable[str],
        concept_ids: Iterable[str] | None = None,
    ) -> CechSolveResult:
        cover = _stable_covering(covering)
        concepts = self._resolve_concepts(cover, concept_ids)
        h1 = self.compute_h1(cover, concepts)
        failed_gluings = tuple(
            overlap for overlap in self.compute_cover_overlaps(cover, concepts)
            if overlap.has_failure
        )
        knowledge_gaps = self.diagnostics.detect_knowledge_gaps(
            self.sheaf, cover, concepts
        )
        polysemy_candidates = self.diagnostics.detect_polysemy(
            self.sheaf, cover, concepts
        )
        global_sections = self.compute_h0(cover, concepts)
        uncertainty = self.diagnostics.classify_uncertainty(
            h1.conflicts, knowledge_gaps, h1.residual
        )
        diagnostics = DiagnosticsOutput(
            global_section_count=len(global_sections),
            conflict_count=len(h1.conflicts),
            knowledge_gap_count=len(knowledge_gaps),
            polysemy_count=len(polysemy_candidates),
            uncertainty=uncertainty,
        )
        return CechSolveResult(
            global_sections=global_sections,
            failed_gluings=failed_gluings,
            conflicts=h1.conflicts,
            knowledge_gaps=knowledge_gaps,
            polysemy_candidates=polysemy_candidates,
            uncertainty=uncertainty,
            diagnostics=diagnostics,
            h1_residual=h1.residual,
        )

    def _resolve_concepts(
        self,
        covering: Iterable[str],
        concept_ids: Iterable[str] | None,
    ) -> tuple[str, ...]:
        if concept_ids is not None:
            return tuple(sorted({str(concept_id) for concept_id in concept_ids}))
        concepts: set[str] = set()
        for ctx_id in covering:
            concepts.update(self.sheaf.sections(ctx_id))
        return tuple(sorted(concepts))


def _sections_for_concept(
    sheaf: SheafStore, covering: Iterable[str], concept_id: str
) -> dict[str, SemanticSection]:
    result: dict[str, SemanticSection] = {}
    for ctx_id in covering:
        section = sheaf.section_store.get(ctx_id, concept_id)
        if section is not None:
            result[ctx_id] = section
    return result


def _stable_covering(covering: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_id in covering:
        ctx_id = str(raw_id or "").strip()
        if ctx_id and ctx_id not in seen:
            seen.add(ctx_id)
            result.append(ctx_id)
    return tuple(result)


def _h1_residual(conflicts: Iterable[CechConflict], threshold: float) -> float:
    conflict_list = tuple(conflicts)
    if not conflict_list:
        return 0.0
    severities = [
        max(0.0, threshold - conflict.similarity)
        for conflict in conflict_list
    ]
    return sum(severities) / len(severities)

