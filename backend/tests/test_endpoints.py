"""Tests for all major endpoints."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("healthy", "degraded")


def test_status(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "stats" in resp.json()


def test_behavioral_patterns(client):
    resp = client.get("/api/behavioral/patterns")
    assert resp.status_code == 200
    assert "patterns" in resp.json()


def test_behavioral_stats(client):
    resp = client.get("/api/behavioral/stats")
    assert resp.status_code == 200


def test_identity_list(client):
    resp = client.get("/api/identity/list")
    assert resp.status_code == 200
    assert "identities" in resp.json()


def test_events_recent(client):
    resp = client.get("/api/events/recent")
    assert resp.status_code == 200
    assert "events" in resp.json()


def test_event_stats(client):
    resp = client.get("/api/events/stats")
    assert resp.status_code == 200


def test_files_list(client):
    resp = client.get("/api/files/list")
    assert resp.status_code == 200


def test_sandbox_info(client):
    resp = client.get("/api/files/sandbox-info")
    assert resp.status_code == 200


def test_network_info(client):
    resp = client.get("/api/network/info")
    assert resp.status_code == 200


def test_exploit_modules(client):
    resp = client.get("/api/exploit/modules")
    assert resp.status_code == 200
    modules = resp.json()["modules"]
    assert "ssh_bruteforce" in modules
    assert "dns_zone_transfer" in modules
    assert "ssl_vulns" in modules


def test_insights_analytics(client):
    resp = client.get("/api/insights/analytics")
    assert resp.status_code == 200


def test_workflows_list(client):
    resp = client.get("/api/workflows/")
    assert resp.status_code == 200


def test_workflow_templates(client):
    resp = client.get("/api/workflows/templates/list")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert "recon" in templates
    assert "track" in templates
    assert "incident" in templates


def test_chat_message(client):
    resp = client.post("/api/chat/message", json={"message": "help"})
    assert resp.status_code == 200
    assert "message" in resp.json()


def test_chat_intents(client):
    resp = client.get("/api/chat/intents")
    assert resp.status_code == 200


def test_settings_get(client):
    resp = client.get("/api/settings/")
    assert resp.status_code == 200


def test_live_dashboard(client):
    resp = client.get("/api/live/dashboard")
    assert resp.status_code == 200
    assert "system" in resp.json()


def test_create_workflow_from_template(client):
    resp = client.post("/api/workflows/", json={
        "template": "recon",
        "input_params": {"target": "127.0.0.1"}
    })
    assert resp.status_code == 200
    assert "workflow_id" in resp.json()
