import pytest

from backend.services.stratum_omnis.csie_cech import CechDiagnostics, CechSolver
from backend.services.stratum_omnis.csie_sheaf import SheafStore, deterministic_vector
from backend.services.stratum_omnis.csie_types import ContextNode, SemanticSection


def _sheaf(dim: int = 8) -> SheafStore:
    return SheafStore(embedding_dim=dim)


def _add_context_with_section(
    sheaf: SheafStore,
    ctx_id: str,
    concept_id: str,
    vector,
    *,
    parents=None,
):
    sheaf.add_context(
        ContextNode(
            id=ctx_id,
            description=ctx_id,
            parent_contexts=parents or [],
            activation_signature=deterministic_vector(ctx_id, sheaf.embedding_dim),
        )
    )
    sheaf.add_section(
        ctx_id,
        concept_id,
        SemanticSection(
            concept_id=concept_id,
            interpretation=vector,
            confidence=1.0,
            source_contexts=[ctx_id],
        ),
    )


def test_h0_success_returns_global_section_when_gluing_passes():
    sheaf = _sheaf()
    vector = deterministic_vector("apple-company", 8)
    _add_context_with_section(sheaf, "ctx:a", "concept:apple", vector)
    _add_context_with_section(sheaf, "ctx:b", "concept:apple", vector)

    solver = CechSolver(sheaf)
    result = solver.validate_global_consistency(["ctx:a", "ctx:b"], ["concept:apple"])

    assert result.uncertainty == "LOW"
    assert result.diagnostics.global_section_count == 1
    assert result.global_sections[0].concept_id == "concept:apple"
    assert result.global_sections[0].source_contexts == ("ctx:a", "ctx:b")
    assert result.conflicts == ()
    assert result.knowledge_gaps == ()


def test_h0_failure_excludes_conflicting_global_section():
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:a", "concept:apple", (1, 0, 0, 0, 0, 0, 0, 0))
    _add_context_with_section(sheaf, "ctx:b", "concept:apple", (-1, 0, 0, 0, 0, 0, 0, 0))

    solver = CechSolver(sheaf)
    global_sections = solver.compute_h0(["ctx:a", "ctx:b"], ["concept:apple"])

    assert global_sections == ()


def test_h1_residual_generation_for_failed_gluing():
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:a", "concept:x", (1, 0, 0, 0, 0, 0, 0, 0))
    _add_context_with_section(sheaf, "ctx:b", "concept:x", (0, 1, 0, 0, 0, 0, 0, 0))

    h1 = CechSolver(sheaf, gluing_threshold=0.7).compute_h1(
        ["ctx:a", "ctx:b"], ["concept:x"]
    )

    assert len(h1.conflicts) == 1
    assert h1.residual == pytest.approx(0.7)
    assert h1.conflicts[0].reason.startswith("Overlap exists")


def test_overlap_computation_reports_shared_and_failed_concepts():
    sheaf = _sheaf()
    same = deterministic_vector("same", 8)
    _add_context_with_section(sheaf, "ctx:a", "concept:shared", same)
    _add_context_with_section(sheaf, "ctx:b", "concept:shared", same)

    overlap = CechSolver(sheaf).compute_cover_overlaps(
        ["ctx:a", "ctx:b"], ["concept:shared"]
    )[0]

    assert overlap.source_context == "ctx:a"
    assert overlap.target_context == "ctx:b"
    assert overlap.shared_concepts == ("concept:shared",)
    assert overlap.similarities["concept:shared"] == pytest.approx(1.0)
    assert overlap.failed_concepts == ()


def test_global_consistency_validation_returns_requested_shape_as_dict():
    sheaf = _sheaf()
    vector = deterministic_vector("stable", 8)
    _add_context_with_section(sheaf, "ctx:a", "concept:x", vector)
    _add_context_with_section(sheaf, "ctx:b", "concept:x", vector)

    payload = CechSolver(sheaf).validate_global_consistency(
        ["ctx:a", "ctx:b"], ["concept:x"]
    ).to_dict()

    assert set(payload) == {
        "global_sections",
        "failed_gluings",
        "conflicts",
        "knowledge_gaps",
        "polysemy_candidates",
        "uncertainty",
        "diagnostics",
        "h1_residual",
    }
    assert payload["diagnostics"] == {
        "global_section_count": 1,
        "conflict_count": 0,
        "knowledge_gap_count": 0,
        "polysemy_count": 0,
        "uncertainty": "LOW",
    }


def test_polysemy_detection_flags_same_identifier_with_different_meanings():
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:company", "concept:apple", (1, 0, 0, 0, 0, 0, 0, 0))
    _add_context_with_section(sheaf, "ctx:fruit", "concept:apple", (-1, 0, 0, 0, 0, 0, 0, 0))

    candidates = CechDiagnostics(gluing_threshold=0.7).detect_polysemy(
        sheaf, ["ctx:company", "ctx:fruit"], ["concept:apple"]
    )

    assert len(candidates) == 1
    assert candidates[0].concept_id == "concept:apple"
    assert candidates[0].contexts == ("ctx:company", "ctx:fruit")


def test_knowledge_gap_detection_for_missing_required_section():
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:a", "concept:x", deterministic_vector("x", 8))
    sheaf.add_context(ContextNode("ctx:b", "B"))

    gaps = CechDiagnostics().detect_knowledge_gaps(
        sheaf, ["ctx:a", "ctx:b"], ["concept:x"]
    )

    assert len(gaps) == 1
    assert gaps[0].context_id == "ctx:b"
    assert gaps[0].concept_id == "concept:x"


def test_uncertainty_classification_low_medium_and_high():
    diagnostics = CechDiagnostics()
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:a", "concept:x", (1, 0, 0, 0, 0, 0, 0, 0))
    _add_context_with_section(sheaf, "ctx:b", "concept:x", (-1, 0, 0, 0, 0, 0, 0, 0))
    conflict = CechSolver(sheaf).compute_h1(["ctx:a", "ctx:b"], ["concept:x"]).conflicts[0]
    gap = diagnostics.detect_knowledge_gaps(sheaf, ["ctx:a"], ["concept:missing"])[0]

    assert diagnostics.classify_uncertainty([], [], 0.0) == "LOW"
    assert diagnostics.classify_uncertainty([conflict], [], 0.0) == "MEDIUM"
    assert diagnostics.classify_uncertainty([conflict], [], 0.1) == "HIGH"
    assert diagnostics.classify_uncertainty([], [gap, gap, gap, gap], 0.0) == "HIGH"


def test_empty_covering_and_empty_concepts_are_safe():
    result = CechSolver(_sheaf()).validate_global_consistency([], [])

    assert result.global_sections == ()
    assert result.conflicts == ()
    assert result.knowledge_gaps == ()
    assert result.uncertainty == "LOW"


def test_summarize_conflicts_returns_compact_records():
    sheaf = _sheaf()
    _add_context_with_section(sheaf, "ctx:a", "concept:x", (1, 0, 0, 0, 0, 0, 0, 0))
    _add_context_with_section(sheaf, "ctx:b", "concept:x", (-1, 0, 0, 0, 0, 0, 0, 0))
    conflicts = CechSolver(sheaf).compute_h1(["ctx:a", "ctx:b"], ["concept:x"]).conflicts

    summary = CechDiagnostics().summarize_conflicts(conflicts)

    assert summary[0]["concept_id"] == "concept:x"
    assert summary[0]["source_context"] == "ctx:a"
    assert summary[0]["target_context"] == "ctx:b"

