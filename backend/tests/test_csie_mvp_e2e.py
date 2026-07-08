from backend.services.stratum_omnis.csie_bootstrap import build_csie_from_profiles
from backend.services.stratum_omnis.csie_cech import CechSolver


def _mvp_profile(stratum_id: str = "STRID-MVP-E2E") -> dict:
    return {
        "stratum_id": stratum_id,
        "identity_anchors": {
            "handle": "mvp-user",
            "platform": "github",
            "resolution_confidence": 0.91,
        },
        "behavioral_intelligence": {
            "digital_activity_score": 72,
            "platform_presence": ["github"],
            "public_repos": 8,
            "followers": 5,
            "peak_activity_hours": [],
            "tech_stack": ["Python", "FastAPI"],
            "contribution_score": 22,
        },
        "situational_intelligence": {
            "country": "UK",
            "city": "",
            "region": "",
            "timezone": "",
            "isp": "",
            "org": "",
            "last_signal": "2026-05-29T00:00:00+00:00",
        },
        "network_signals": {
            "ip": "",
            "open_ports": [],
            "services": [],
            "hostnames": [],
            "vulnerabilities": [],
        },
        "risk_profile": {
            "overall_risk": "LOW",
            "exposed_services": 0,
            "vulnerability_count": 0,
        },
        "metadata": {
            "source": "public_github",
            "collection_date": "2026-05-29T00:00:00+00:00",
            "country": "UK",
            "data_type": "public_signal",
            "safe_mode": True,
        },
        "raw_signals": {"github_search": {"login": "mvp-user"}},
    }


def test_csie_mvp_end_to_end_profile_to_runtime_response(monkeypatch):
    import backend.services.stratum_omnis.csie as csie_runtime

    profile = _mvp_profile()
    bootstrap = build_csie_from_profiles([profile])
    conversion = bootstrap.conversions[0]

    assert conversion.stratum_id == profile["stratum_id"]
    assert conversion.identity_object_id in bootstrap.category.objects
    assert conversion.context_ids
    assert conversion.section_ids
    assert conversion.morphism_ids

    for ctx_id in conversion.context_ids:
        assert ctx_id in bootstrap.sheaf.contexts
    for ctx_id, concept_id in conversion.section_ids:
        assert bootstrap.sheaf.section_store.get(ctx_id, concept_id) is not None

    solver = CechSolver(bootstrap.sheaf)
    covering = bootstrap.sheaf.get_covering(conversion.context_ids)
    concept_ids = tuple(sorted({concept_id for _, concept_id in conversion.section_ids}))
    h0_sections = solver.compute_h0(covering, concept_ids)
    h1_result = solver.compute_h1(covering, concept_ids)
    result = solver.validate_global_consistency(covering, concept_ids)

    assert covering
    assert result.global_sections == h0_sections
    assert result.conflicts == h1_result.conflicts
    assert result.h1_residual == h1_result.residual
    assert result.diagnostics.global_section_count == len(result.global_sections)
    assert result.diagnostics.conflict_count == len(result.conflicts)
    assert result.diagnostics.knowledge_gap_count == len(result.knowledge_gaps)
    assert result.diagnostics.polysemy_count == len(result.polysemy_candidates)
    assert result.uncertainty in {"LOW", "MEDIUM", "HIGH"}
    assert isinstance(result.h1_residual, float)

    monkeypatch.setattr(csie_runtime, "load_stratum_profiles", lambda limit=10: [profile][:limit])
    snapshot = csie_runtime.get_csie_snapshot(limit=1)

    assert snapshot["count"] == 1
    assert snapshot["csie_engine"] == {
        "mode": "mvp_cech",
        "version": "day4",
        "available": True,
    }

    row = snapshot["classifications"][0]
    assert row["stratum_id"] == profile["stratum_id"]
    assert {"semantic_objects", "morphisms", "context"}.issubset(row)
    assert row["context"]["platform"] == "github"
    assert row["context"]["source"] == "public_github"

    assert row["csie_engine"] == {"mode": "mvp_cech", "version": "day4"}
    assert isinstance(row["covering"], list)
    assert set(row["global_section_summary"]) == {"count", "concept_ids"}
    assert isinstance(row["global_section_summary"]["count"], int)
    assert isinstance(row["global_section_summary"]["concept_ids"], list)
    assert isinstance(row["h1_residual"], float)
    assert row["uncertainty_level"] in {"LOW", "MEDIUM", "HIGH"}
    assert set(row["diagnostics"]) == {
        "global_section_count",
        "conflict_count",
        "knowledge_gap_count",
        "polysemy_count",
        "uncertainty",
    }
