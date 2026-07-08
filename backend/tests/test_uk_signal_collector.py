from backend.services.uk_signal_collector import CollectionJob, collector


def test_uk_collection_status_not_found(client):
    resp = client.get("/api/osint/collect/status/does-not-exist")
    assert resp.status_code == 404


def test_uk_collection_start_endpoint(client, monkeypatch):
    async def fake_start_collection(**kwargs):
        return CollectionJob(
            job_id="uksig-test1234",
            status="running",
            target_profiles=kwargs["target_profiles"],
            github_queries=kwargs.get("github_queries") or ['location:"UK"'],
            allowlisted_domains=kwargs.get("allowlisted_domains") or [],
            hostsearch_zones=kwargs.get("hostsearch_zones") or [".co.uk"],
            gitlab_queries=kwargs.get("gitlab_queries") or ["uk"],
            npm_queries=kwargs.get("npm_queries") or ["uk"],
            pypi_packages=kwargs.get("pypi_packages") or ["django-localflavor"],
            govuk_queries=kwargs.get("govuk_queries") or ["uk"],
            spending_queries=kwargs.get("spending_queries") or ["UK public contracts awards"],
            gdelt_queries=kwargs.get("gdelt_queries") or ["United Kingdom policy"],
            osm_queries=kwargs.get("osm_queries") or ["London, United Kingdom"],
            max_github_pages=kwargs["max_github_pages"],
            max_github_enrichments=kwargs["max_github_enrichments"],
            max_hostsearch_results_per_zone=kwargs.get("max_hostsearch_results_per_zone", 1),
            max_ipinfo_lookups=kwargs.get("max_ipinfo_lookups", 0),
            max_gitlab_results_per_query=kwargs.get("max_gitlab_results_per_query", 1),
            max_npm_results_per_query=kwargs.get("max_npm_results_per_query", 1),
            max_pypi_package_lookups=kwargs.get("max_pypi_package_lookups", 1),
            max_govuk_results_per_query=kwargs.get("max_govuk_results_per_query", 1),
            max_spending_results_per_query=kwargs.get("max_spending_results_per_query", 1),
            max_gdelt_results_per_query=kwargs.get("max_gdelt_results_per_query", 1),
            max_osm_results_per_query=kwargs.get("max_osm_results_per_query", 1),
            total_units=1,
        )

    monkeypatch.setattr(collector, "start_collection", fake_start_collection)

    resp = client.post(
        "/api/osint/collect/uk",
        json={"target_profiles": 250, "allowlisted_domains": ["example.co.uk"]},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["job_id"] == "uksig-test1234"
    assert payload["status"] == "running"
    assert payload["mode"] == "public_profile_safe"


def test_uk_collection_export_reads_stratum_profiles(client):
    from backend.database import db

    job_id = "uksig-exporttest"
    job = CollectionJob(
        job_id=job_id,
        status="completed",
        target_profiles=1,
        github_queries=['location:"UK"'],
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
    collector._jobs[job_id] = job

    try:
        db.upsert_identity(
            {
                "name": "octocat-uk",
                "platform": "github",
                "handle": "octocat-uk",
                "extra": {
                    "stratum_id": "STRID-TEST0001",
                    "identity_anchors": {
                        "handle": "octocat-uk",
                        "platform": "github",
                        "resolution_confidence": 0.9,
                    },
                    "behavioral_intelligence": {
                        "digital_activity_score": 42,
                        "platform_presence": ["github"],
                        "public_repos": 3,
                        "followers": 7,
                        "peak_activity_hours": [],
                        "tech_stack": [],
                        "contribution_score": 21,
                    },
                    "situational_intelligence": {
                        "country": "UK",
                        "city": "London",
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
                    "raw_signals": {
                        "github_search": {
                            "login": "octocat-uk",
                            "score": 1.0,
                            "profile_url": "https://github.com/octocat-uk",
                        }
                    },
                },
            }
        )

        resp = client.get(f"/api/osint/collect/export/{job_id}")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["job_id"] == job_id
        assert payload["count"] == 1
        assert payload["profiles"][0]["metadata"]["collection_job_id"] == job_id
    finally:
        collector._jobs.pop(job_id, None)
