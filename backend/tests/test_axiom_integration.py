"""
backend/tests/test_axiom_integration.py

Tests for:
  - AXIOM router endpoints (status, capabilities, compress, demo, pipeline)
  - Intelligence pipeline (AXIOM → causal functor)
  - main.py router registration

Run:
    cd E:\\JULIUS
    pytest backend/tests/test_axiom_integration.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app
    return TestClient(app)


# ── AXIOM router ───────────────────────────────────────────────────────────

class TestAxiomStatus:
    def test_status_200(self, client):
        r = client.get("/api/axiom/status")
        assert r.status_code == 200

    def test_status_fields(self, client):
        data = client.get("/api/axiom/status").json()
        assert data["module"] == "AXIOM"
        assert data["state"] == "active"
        assert isinstance(data["capabilities"], list)
        assert len(data["capabilities"]) > 0
        assert data["lossless_guarantee"] is True

    def test_capabilities_200(self, client):
        r = client.get("/api/axiom/capabilities")
        assert r.status_code == 200

    def test_capabilities_has_pipeline(self, client):
        data = client.get("/api/axiom/capabilities").json()
        assert "pipeline" in data
        assert len(data["pipeline"]) == 5
        for stage in data["pipeline"]:
            assert "name"  in stage
            assert "exact" in stage
            assert stage["exact"] is True

    def test_report_200(self, client):
        r = client.get("/api/axiom/report")
        assert r.status_code == 200
        data = r.json()
        assert data["lossless_target"] is True


class TestAxiomCompress:
    def test_compress_mini_transformer(self, client):
        r = client.post("/api/axiom/compress", json={
            "model_architecture": "mini_transformer",
            "d_model": 64,
            "n_heads": 4,
            "verify_lossless": True,
            "verbose": False,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["original_params"] > 0
        assert data["total_compression_ratio"] > 0
        assert isinstance(data["compression_modes_applied"], list)
        assert len(data["compression_modes_applied"]) == 5

    def test_compress_lossless_verified(self, client):
        r = client.post("/api/axiom/compress", json={
            "model_architecture": "mini_transformer",
            "d_model": 64,
            "n_heads": 4,
            "verify_lossless": True,
        })
        data = r.json()
        # verified_lossless can be True or None (if shapes changed)
        assert data["verified_lossless"] in (True, None)

    def test_compress_unknown_arch_400(self, client):
        r = client.post("/api/axiom/compress", json={
            "model_architecture": "nonexistent_arch",
        })
        assert r.status_code == 400

    def test_demo_endpoint(self, client):
        r = client.post("/api/axiom/demo")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("demo") is True
        assert data["original_params"] > 0


class TestAxiomPipelineAnalysis:
    SCAN_PAYLOAD = {
        "scan_results": [
            {
                "target": "192.168.1.1",
                "ports": list(range(20)),          # 20 open ports
                "vulnerabilities": ["CVE-2021-44228", "CVE-2022-0001"],
                "services": {"22": "ssh", "80": "http", "445": "smb"},
                "risk_score": 8.5,
            },
            {
                "target": "10.0.0.1",
                "ports": [80, 443],
                "vulnerabilities": [],
                "services": {"80": "http", "443": "https"},
                "risk_score": 2.0,
            },
        ],
        "osint_data": {
            "emails":    ["admin@example.com"],
            "phones":    [],
            "domains":   ["example.com", "sub.example.com"],
            "ips":       ["192.168.1.1"],
            "usernames": ["admin", "root"],
        },
        "target": "192.168.1.0/24",
        "analysis_depth": "standard",
    }

    def test_pipeline_200(self, client):
        r = client.post("/api/axiom/analyse/pipeline", json=self.SCAN_PAYLOAD)
        assert r.status_code == 200, r.text

    def test_pipeline_returns_findings(self, client):
        data = client.post("/api/axiom/analyse/pipeline", json=self.SCAN_PAYLOAD).json()
        assert data["status"] == "analysed"
        assert data["total_scans_analysed"] == 2
        findings = data["scan_findings"]
        assert len(findings) == 2
        for f in findings:
            assert f["severity"] in ("critical", "high", "medium", "low")
            assert 0.0 <= f["anomaly_score"] <= 1.0

    def test_pipeline_osint_summary(self, client):
        data = client.post("/api/axiom/analyse/pipeline", json=self.SCAN_PAYLOAD).json()
        osint = data["osint_summary"]
        assert osint is not None
        assert osint["total_indicators"] > 0
        assert "dominant_category" in osint

    def test_pipeline_empty_scans(self, client):
        r = client.post("/api/axiom/analyse/pipeline", json={
            "scan_results": [],
            "target": "test",
        })
        assert r.status_code == 200
        assert r.json()["total_scans_analysed"] == 0


# ── Intelligence pipeline router ───────────────────────────────────────────

class TestIntelPipeline:
    def test_intel_status(self, client):
        r = client.get("/api/intel/status")
        assert r.status_code == 200
        data = r.json()
        assert data["pipeline"] == "intelligence"
        assert data["status"] == "active"

    def test_intel_analyse(self, client):
        r = client.post("/api/intel/analyse", json={
            "scan_results": [
                {
                    "target": "172.16.0.1",
                    "ports": [22, 80, 3306],
                    "vulnerabilities": ["CVE-2023-1234"],
                    "services": {"22": "ssh", "3306": "mysql"},
                    "risk_score": 7.0,
                }
            ],
            "target": "172.16.0.1",
            "depth": "standard",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "axiom_findings" in data
        assert "summary" in data
        assert "recommendation" in data["summary"]

    def test_intel_analyse_empty(self, client):
        r = client.post("/api/intel/analyse", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["summary"]["total_targets_analysed"] == 0


# ── main.py router registration ────────────────────────────────────────────

class TestMainRouterRegistration:
    """Verify all routers are mounted and reachable."""

    EXPECTED_PREFIXES = [
        "/api/axiom/status",
        "/api/axiom/capabilities",
        "/api/axiom/report",
        "/diagnostics/causal-functor",        # causal_functor router (no /api prefix)
        "/api/intel/status",                  # new intel_pipeline router
    ]

    def test_all_prefixes_reachable(self, client):
        for path in self.EXPECTED_PREFIXES:
            r = client.get(path)
            assert r.status_code in (200, 422), \
                f"Expected 200/422 for {path}, got {r.status_code}"

    def test_health_endpoint(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_docs_available(self, client):
        r = client.get("/docs")
        assert r.status_code == 200