import backend.routers.live as live_router


def test_live_ip_alias_route(client, monkeypatch):
    async def fake_lookup(ip_address: str):
        return {
            "ip": ip_address,
            "country": "United States",
            "city": "Mountain View",
            "org": "Google LLC",
            "lat": 37.386,
            "lon": -122.0838,
            "intel": {"network_type": "Public Internet"},
            "checked_at": "2026-05-23T00:00:00",
        }

    monkeypatch.setattr(live_router, "_lookup_ip_payload", fake_lookup)

    resp = client.get("/api/live/ip/8.8.8.8")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ip"] == "8.8.8.8"
    assert body["country"] == "United States"
    assert body["city"] == "Mountain View"
    assert body["org"] == "Google LLC"


def test_live_dns_alias_route(client, monkeypatch):
    async def fake_lookup(domain: str):
        return {
            "domain": domain,
            "records": [{"type": "A", "address": "142.250.72.14"}],
            "dns": {"resolved": True, "a_records": ["142.250.72.14"]},
            "checked_at": "2026-05-23T00:00:00",
        }

    monkeypatch.setattr(live_router, "_lookup_dns_payload", fake_lookup)

    resp = client.get("/api/live/dns/google.com")
    assert resp.status_code == 200
    body = resp.json()
    assert body["domain"] == "google.com"
    assert body["records"][0]["address"] == "142.250.72.14"
    assert body["dns"]["resolved"] is True


def test_live_cves_alias_route(client, monkeypatch):
    async def fake_cves():
        return {
            "cves": [
                {
                    "id": "CVE-2026-0001",
                    "description": "Test vulnerability",
                    "severity": "high",
                    "published": "2026-05-23T00:00:00.000",
                }
            ],
            "total_results": 1,
            "fetched_at": "2026-05-23T00:00:00",
        }

    monkeypatch.setattr(live_router, "_fetch_latest_cves_payload", fake_cves)

    resp = client.get("/api/live/cves")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_results"] == 1
    assert body["cves"][0]["id"] == "CVE-2026-0001"
