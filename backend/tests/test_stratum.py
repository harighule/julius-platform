from backend.services.uk_signal_collector import CollectionJob, collector


def _persist_test_stratum_profile(job_id: str = "uksig-test-csie"):
    from backend.database import db

    db.upsert_identity(
        {
            "name": "csie-user",
            "platform": "github",
            "handle": "csie-user",
            "extra": {
                "stratum_id": "STRID-CSIE1",
                "identity_anchors": {
                    "handle": "csie-user",
                    "platform": "github",
                    "resolution_confidence": 0.88,
                },
                "behavioral_intelligence": {
                    "digital_activity_score": 50,
                    "platform_presence": ["github"],
                    "public_repos": 4,
                    "followers": 3,
                    "peak_activity_hours": [],
                    "tech_stack": ["Python"],
                    "contribution_score": 16,
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
                    "collection_job_id": job_id,
                    "safe_mode": True,
                },
                "raw_signals": {"github_search": {"login": "csie-user"}},
            },
        }
    )


def test_stratum_blueprint(client):
    resp = client.get("/api/stratum/blueprint")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["name"] == "STRATUM OMNIS"
    assert len(payload["layers"]) == 9
    assert any(source["source_id"] == "gdelt_public_events" for source in payload["signal_sources"])


def test_stratum_runtime(client):
    resp = client.get("/api/stratum/runtime")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["mode"] == "safe_public_only"
    assert "stats" in payload
    assert "runtime" in payload


def test_stratum_feature_oracle_csie_endpoints(client):
    _persist_test_stratum_profile()

    feature_resp = client.get("/api/stratum/feature-store?limit=5")
    stream_resp = client.get("/api/stratum/stream-processing?limit=5")
    identity_resp = client.get("/api/stratum/identity-resolution?limit=5")
    model_hub_resp = client.get("/api/stratum/model-hub")
    oracle_resp = client.get("/api/stratum/oracle?limit=5")
    csie_resp = client.get("/api/stratum/csie?limit=5")

    assert feature_resp.status_code == 200
    assert stream_resp.status_code == 200
    assert identity_resp.status_code == 200
    assert model_hub_resp.status_code == 200
    assert oracle_resp.status_code == 200
    assert csie_resp.status_code == 200

    assert "features" in feature_resp.json()
    assert "recent_stream_events" in stream_resp.json()
    assert "resolved_identities" in identity_resp.json()
    assert "registry" in model_hub_resp.json()
    assert "predictions" in oracle_resp.json()
    csie_payload = csie_resp.json()
    assert "classifications" in csie_payload
    assert csie_payload["csie_engine"]["mode"] == "mvp_cech"
    assert csie_payload["csie_engine"]["version"] == "day4"

    row = csie_payload["classifications"][0]
    assert {"stratum_id", "semantic_objects", "morphisms", "context"}.issubset(row)
    assert {"csie_engine", "covering", "global_section_summary", "h1_residual", "uncertainty_level", "diagnostics"}.issubset(row)
    assert row["csie_engine"]["mode"] == "mvp_cech"
    assert row["csie_engine"]["version"] == "day4"
    assert isinstance(row["covering"], list)
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

    csie_registry = next(
        item for item in model_hub_resp.json()["registry"]
        if item["model_id"] == "stratum.csie.v1"
    )
    assert csie_registry["engine"]["mode"] == "mvp_cech"
    assert csie_registry["engine"]["version"] == "day4"


def test_export_works_for_persisted_job_without_live_registry(client):
    from backend.database import db

    job_id = "uksig-persisted"
    collector._jobs[job_id] = CollectionJob(
        job_id=job_id,
        status="completed",
        target_profiles=1,
        github_queries=["location:UK"],
        allowlisted_domains=[],
        hostsearch_zones=[],
        gitlab_queries=[],
        npm_queries=[],
        pypi_packages=[],
        govuk_queries=[],
        spending_queries=[],
        gdelt_queries=[],
        osm_queries=[],
        max_github_pages=1,
        max_github_enrichments=0,
        max_hostsearch_results_per_zone=1,
        max_ipinfo_lookups=0,
        max_gitlab_results_per_query=1,
        max_npm_results_per_query=1,
        max_pypi_package_lookups=0,
        max_govuk_results_per_query=1,
        max_spending_results_per_query=1,
        max_gdelt_results_per_query=1,
        max_osm_results_per_query=1,
        total_units=1,
    )
    db.upsert_identity(
        {
            "name": "persisted-user",
            "platform": "github",
            "handle": "persisted-user",
            "extra": {
                "stratum_id": "STRID-PERSIST1",
                "identity_anchors": {
                    "handle": "persisted-user",
                    "platform": "github",
                    "resolution_confidence": 0.88,
                },
                "behavioral_intelligence": {
                    "digital_activity_score": 50,
                    "platform_presence": ["github"],
                    "public_repos": 4,
                    "followers": 3,
                    "peak_activity_hours": [],
                    "tech_stack": [],
                    "contribution_score": 16,
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
                    "collection_job_id": job_id,
                    "safe_mode": True,
                },
                "raw_signals": {"github_search": {"login": "persisted-user"}},
            },
        }
    )
    collector._jobs.pop(job_id, None)

    status_resp = client.get(f"/api/osint/collect/status/{job_id}")
    export_resp = client.get(f"/api/osint/collect/export/{job_id}")

    assert status_resp.status_code == 200
    assert export_resp.status_code == 200
    assert export_resp.json()["count"] >= 1
