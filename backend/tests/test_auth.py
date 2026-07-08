"""Tests for authentication endpoints."""


def test_auth_status(client):
    resp = client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["available"] is True


def test_login_success(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "TestAdmin@1234"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["username"] == "admin"


def test_login_failure(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_endpoint(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"


def test_me_without_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401
