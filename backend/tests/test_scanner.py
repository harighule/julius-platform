"""Tests for scanner endpoints."""


def test_scan_list(client, auth_headers):
    resp = client.get("/api/scanner/scans")
    assert resp.status_code == 200
    assert "scans" in resp.json()


def test_start_scan(client, auth_headers):
    resp = client.post("/api/scanner/scan", json={"target": "127.0.0.1", "scan_type": "quick"})
    assert resp.status_code == 200
    data = resp.json()
    assert "scan_id" in data
    assert data["status"] == "running"


def test_vulnerability_list(client, auth_headers):
    resp = client.get("/api/scanner/vulnerabilities")
    assert resp.status_code == 200
    assert "vulnerabilities" in resp.json()


def test_port_check(client, auth_headers):
    resp = client.post("/api/scanner/check-port", json={"ip": "127.0.0.1", "port": 8000})
    assert resp.status_code == 200
    assert resp.json()["status"] in ("open", "closed", "filtered")
