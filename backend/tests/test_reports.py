from pathlib import Path


def test_full_report_generation_and_downloads(client, monkeypatch, tmp_path):
    from backend.services import intelligence_report as service

    async def fake_collect():
        return {
            "title": "JULIUS INTELLIGENCE REPORT",
            "subtitle": "Cyber Threat Intelligence Analysis",
            "classification": "UNCLASSIFIED",
            "summary": {
                "generated_at": "2026-05-23T12:00:00",
                "scan_count": 2,
                "open_port_count": 5,
                "vulnerability_count": 2,
                "event_count": 8,
                "darkweb_investigations": 1,
                "threat_entries": 3,
                "identity_profiles": 1,
                "latest_cves": 2,
            },
            "scanner": {
                "targets": [
                    {
                        "target": "10.0.0.5",
                        "status": "completed",
                        "open_ports": [{"port": 22}, {"port": 443}],
                        "vulnerability_count": 1,
                    }
                ],
                "vulnerabilities": [
                    {
                        "severity": "critical",
                        "host": "10.0.0.5",
                        "port": 443,
                        "service": "https",
                        "title": "TLS Exposure",
                        "cve_id": "CVE-2026-0001",
                    },
                    {
                        "severity": "medium",
                        "host": "10.0.0.8",
                        "port": 80,
                        "service": "http",
                        "title": "Outdated Service",
                        "cve_id": "CVE-2026-0002",
                    },
                ],
                "vulnerability_counts": {
                    "CRITICAL": 1,
                    "HIGH": 0,
                    "MEDIUM": 1,
                    "LOW": 0,
                    "INFO": 0,
                    "UNKNOWN": 0,
                },
                "vulnerability_count": 2,
            },
            "events": {
                "total_events": 8,
                "distribution": {"scan_completed": 5, "darkweb_hit": 3},
                "recent": [],
            },
            "darkweb": {
                "total": 1,
                "completed": 1,
                "failed": 0,
                "active": 0,
                "investigations": [
                    {
                        "query": "acme leak",
                        "status": "completed",
                        "raw_results_count": 226,
                        "filtered_count": 20,
                        "scraped_count": 5,
                    }
                ],
            },
            "threat_feeds": {
                "count": 3,
                "sources": {"feodo_tracker": 1, "emerging_threats": 1, "cins_score": 1},
                "severity_counts": {
                    "CRITICAL": 1,
                    "HIGH": 1,
                    "MEDIUM": 1,
                    "LOW": 0,
                    "INFO": 0,
                    "UNKNOWN": 0,
                },
                "entries": [],
            },
            "identities": {
                "count": 1,
                "profiles": [
                    {
                        "name": "Jane Analyst",
                        "platform": "LinkedIn",
                        "email": "jane@example.com",
                        "phone": "+1-555-0100",
                        "handle": "@jane",
                    }
                ],
            },
            "live_tools": {
                "ip_lookup": {"ip": "8.8.8.8"},
                "dns_lookup": {"domain": "example.com"},
                "cves": {
                    "cves": [
                        {
                            "severity": "high",
                            "id": "CVE-2026-1001",
                            "published": "2026-05-23",
                            "description": "Example issue one",
                        },
                        {
                            "severity": "low",
                            "id": "CVE-2026-1002",
                            "published": "2026-05-22",
                            "description": "Example issue two",
                        },
                    ]
                },
            },
            "recommendations": [
                "Patch externally exposed services.",
                "Review dark web findings for credential exposure.",
            ],
        }

    monkeypatch.setattr(service, "_collect_report_data", fake_collect)
    monkeypatch.setattr(service, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(service, "_generated_reports", {})
    Path(tmp_path).mkdir(parents=True, exist_ok=True)

    create_resp = client.post("/api/reports/full/generate")
    assert create_resp.status_code == 200
    body = create_resp.json()

    assert body["report_id"].startswith("julius-report-")
    assert body["downloads"]["docx"].endswith("/docx")
    assert body["downloads"]["pdf"].endswith("/pdf")

    docx_resp = client.get(body["downloads"]["docx"])
    assert docx_resp.status_code == 200
    assert (
        docx_resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

    pdf_resp = client.get(body["downloads"]["pdf"])
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"

    report_id = body["report_id"]
    assert (tmp_path / f"{report_id}.docx").exists()
    assert (tmp_path / f"{report_id}.pdf").exists()
