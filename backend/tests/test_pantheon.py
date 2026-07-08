"""Contract tests for PANTHEON control-plane endpoints."""

import uuid


def test_pantheon_modules_inventory(client, auth_headers):
    resp = client.get("/api/v1/pantheon/modules", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 27
    assert len(data["items"]) == 27


def test_pantheon_registry_status(client, auth_headers):
    resp = client.get("/api/v1/pantheon/registry/status", headers=auth_headers)
    assert resp.status_code == 200
    modules = resp.json()["modules"]
    assert len(modules) == 27


def test_pantheon_events_publish_and_list(client, auth_headers):
    body = {
        "module": "nexus_gate",
        "event_type": "payment.instructions",
        "entity_id": "pay-1",
        "payload": {"amount": 100},
        "idempotency_key": "idem-test-events-1",
    }
    r1 = client.post("/api/v1/pantheon/events", json=body, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["success"] is True
    ev = r1.json().get("event") or {}
    assert ev.get("integrity_hash") and len(str(ev["integrity_hash"])) == 64
    from backend.services.pantheon.event_integrity import compute_pantheon_event_integrity_hash

    assert compute_pantheon_event_integrity_hash(ev) == ev["integrity_hash"]
    r2 = client.post("/api/v1/pantheon/events", json=body, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json().get("idempotent_replay") is True

    listed = client.get("/api/v1/pantheon/events?limit=10", headers=auth_headers)
    assert listed.status_code == 200
    listed_body = listed.json()
    items = listed_body["items"]
    assert listed_body.get("count") == len(items)
    match = next((e for e in items if e.get("idempotency_key") == "idem-test-events-1"), None)
    assert match is not None
    assert match.get("actor_username") == "admin"
    assert match.get("subject_claims_json")

    filtered = client.get(
        "/api/v1/pantheon/events?limit=50&module=nexus_gate&event_type=payment.instructions",
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    for row in filtered.json().get("items", []):
        assert row.get("module") == "nexus_gate"
        assert row.get("event_type") == "payment.instructions"


def test_pantheon_events_rejects_unknown_module(client, auth_headers):
    r = client.post(
        "/api/v1/pantheon/events",
        json={
            "module": "not_a_contract_module",
            "event_type": "x.y",
            "entity_id": "e1",
            "payload": {},
            "idempotency_key": f"idem-bad-mod-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "unknown_module" in str(r.json())


def test_pantheon_events_rejects_oversized_payload(client, auth_headers):
    r = client.post(
        "/api/v1/pantheon/events",
        json={
            "module": "nexus_gate",
            "event_type": "x.large",
            "entity_id": "e1",
            "payload": {"blob": "x" * 70000},
            "idempotency_key": f"idem-big-{uuid.uuid4().hex[:8]}",
        },
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "payload_size" in str(r.json())


def test_pantheon_events_verify_integrity_batch(client, auth_headers):
    body = {
        "module": "nexus_gate",
        "event_type": "integrity.batch",
        "entity_id": "e-batch",
        "payload": {},
        "idempotency_key": f"idem-batch-{uuid.uuid4().hex}",
    }
    posted = client.post("/api/v1/pantheon/events", json=body, headers=auth_headers)
    assert posted.status_code == 200
    eid = posted.json()["event"]["event_id"]
    batch = client.post(
        "/api/v1/pantheon/events/verify-integrity",
        json={"event_ids": [eid, "nonexistent-event-id", eid]},
        headers=auth_headers,
    )
    assert batch.status_code == 200
    data = batch.json()
    assert data["count"] == 2
    by_id = {x["event_id"]: x for x in data["items"]}
    assert by_id[eid]["integrity_valid"] is True
    assert by_id["nonexistent-event-id"]["integrity_valid"] is False
    assert by_id["nonexistent-event-id"].get("reason") == "not_found"

    too_many = client.post(
        "/api/v1/pantheon/events/verify-integrity",
        json={"event_ids": [f"id-{i}" for i in range(51)]},
        headers=auth_headers,
    )
    assert too_many.status_code == 400


def test_pantheon_event_get_by_id(client, auth_headers):
    body = {
        "module": "nexus_gate",
        "event_type": "detail.probe",
        "entity_id": "e-detail",
        "payload": {"k": 2},
        "idempotency_key": f"idem-detail-{uuid.uuid4().hex}",
    }
    posted = client.post("/api/v1/pantheon/events", json=body, headers=auth_headers)
    assert posted.status_code == 200
    eid = posted.json()["event"]["event_id"]
    got = client.get(f"/api/v1/pantheon/events/{eid}", headers=auth_headers)
    assert got.status_code == 200
    ev = got.json().get("event") or {}
    assert ev.get("event_id") == eid
    assert ev.get("event_type") == "detail.probe"
    assert ev.get("payload") == {"k": 2}
    miss = client.get("/api/v1/pantheon/events/no-such-event", headers=auth_headers)
    assert miss.status_code == 404


def test_pantheon_event_integrity_endpoint(client, auth_headers):
    body = {
        "module": "nexus_gate",
        "event_type": "integrity.probe",
        "entity_id": "e-int",
        "payload": {"n": 1},
        "idempotency_key": f"idem-integ-{uuid.uuid4().hex}",
    }
    posted = client.post("/api/v1/pantheon/events", json=body, headers=auth_headers)
    assert posted.status_code == 200
    eid = posted.json()["event"]["event_id"]
    chk = client.get(f"/api/v1/pantheon/events/{eid}/integrity", headers=auth_headers)
    assert chk.status_code == 200
    data = chk.json()
    assert data.get("integrity_valid") is True
    assert data.get("stored_hash") == data.get("computed_hash")
    missing = client.get("/api/v1/pantheon/events/nonexistent-event-id/integrity", headers=auth_headers)
    assert missing.status_code == 404


def test_pantheon_events_publish_rate_limit_429(client, auth_headers, monkeypatch):
    monkeypatch.setenv("PANTHEON_MUTATION_RATE_PER_MINUTE", "2")
    for i in range(2):
        resp = client.post(
            "/api/v1/pantheon/events",
            json={
                "module": "nexus_gate",
                "event_type": "rate.test",
                "entity_id": f"e-{i}",
                "payload": {},
                "idempotency_key": f"idem-rate-{uuid.uuid4().hex}",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
    blocked = client.post(
        "/api/v1/pantheon/events",
        json={
            "module": "nexus_gate",
            "event_type": "rate.test",
            "entity_id": "e-blocked",
            "payload": {},
            "idempotency_key": f"idem-rate-{uuid.uuid4().hex}",
        },
        headers=auth_headers,
    )
    assert blocked.status_code == 429


def test_pantheon_conditions_evaluate_idempotent(client, auth_headers):
    body = {
        "idempotency_key": "idem-test-conditions-1",
        "payment": {
            "payment_id": "p-cond-1",
            "amount": 1500,
            "risk_score": 0.35,
            "beneficiary_id": "beneficiary-1",
        },
        "conditions": [
            {"code": "MAX_AMOUNT", "config": {"threshold": 2500}},
            {"code": "RISK_SCORE", "config": {"max_score": 0.6}},
        ],
    }
    r1 = client.post("/api/v1/pantheon/conditions/evaluate", json=body, headers=auth_headers)
    assert r1.status_code == 200
    r2 = client.post("/api/v1/pantheon/conditions/evaluate", json=body, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json().get("idempotent_replay") is True


def test_pantheon_taxon_compute_idempotent(client, auth_headers):
    body = {
        "idempotency_key": "idem-test-taxon-1",
        "payment_id": "p-tax-1",
        "payment_type": "VENDOR_PAYMENT",
        "gross_amount": 10000,
        "category_code": "CONTRACTOR",
    }
    r1 = client.post("/api/v1/pantheon/taxon/compute", json=body, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json().get("receipt_hash")
    assert r1.json().get("receipt_version") == 1
    r2 = client.post("/api/v1/pantheon/taxon/compute", json=body, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json().get("idempotent_replay") is True


def test_taxon_compute_appends_prism_mirror(client, auth_headers):
    before = client.get("/api/v1/pantheon/audit/verify", headers=auth_headers)
    assert before.status_code == 200
    n0 = before.json().get("records", 0)

    body = {
        "idempotency_key": f"idem-taxon-prism-{uuid.uuid4().hex}",
        "payment_id": f"p-prism-{uuid.uuid4().hex[:8]}",
        "payment_type": "VENDOR_PAYMENT",
        "gross_amount": 333,
        "category_code": "CONTRACTOR",
    }
    comp = client.post("/api/v1/pantheon/taxon/compute", json=body, headers=auth_headers)
    assert comp.status_code == 200
    assert comp.json().get("receipt_hash")

    after = client.get("/api/v1/pantheon/audit/verify", headers=auth_headers)
    assert after.status_code == 200
    n1 = after.json().get("records", 0)
    assert n1 >= n0 + 1

    comp2 = client.post("/api/v1/pantheon/taxon/compute", json=body, headers=auth_headers)
    assert comp2.status_code == 200
    assert comp2.json().get("idempotent_replay") is True
    after2 = client.get("/api/v1/pantheon/audit/verify", headers=auth_headers)
    assert after2.json().get("records", 0) == n1


def test_pantheon_taxon_receipts_list(client, auth_headers):
    body = {
        "idempotency_key": f"idem-test-taxon-receipt-{uuid.uuid4().hex[:8]}",
        "payment_id": "p-tax-receipt-1",
        "payment_type": "VENDOR_PAYMENT",
        "gross_amount": 5000,
        "category_code": "CONTRACTOR",
    }
    comp = client.post("/api/v1/pantheon/taxon/compute", json=body, headers=auth_headers)
    assert comp.status_code == 200
    h = comp.json().get("receipt_hash")
    assert h

    listed = client.get("/api/v1/pantheon/taxon/receipts?limit=20", headers=auth_headers)
    assert listed.status_code == 200
    data = listed.json()
    assert data["count"] >= 1
    match = next((x for x in data["items"] if x.get("idempotency_key") == body["idempotency_key"]), None)
    assert match is not None
    assert match.get("receipt_hash") == h


def test_tax_computation_receipt_hash_stable():
    from backend.services.pantheon.taxon import compute_tax, tax_computation_receipt_hash

    req = {
        "payment_id": "p-stable",
        "payment_type": "VENDOR_PAYMENT",
        "gross_amount": 100.0,
        "category_code": "CONTRACTOR",
        "metadata": {},
    }
    result = compute_tax(req)
    assert tax_computation_receipt_hash(req, result) == tax_computation_receipt_hash(req, result)


def test_pantheon_audit_recent_tail(client, auth_headers):
    append = client.post(
        "/api/v1/pantheon/audit/append",
        json={
            "module": "prism_audit",
            "event_type": "test.recent_tail",
            "entity_id": "ent-recent-1",
            "payload": {"marker": "recent-tail-test"},
        },
        headers=auth_headers,
    )
    assert append.status_code == 200

    recent = client.get("/api/v1/pantheon/audit/recent?limit=10", headers=auth_headers)
    assert recent.status_code == 200
    data = recent.json()
    assert data["count"] >= 1
    match = next((x for x in data["items"] if x.get("entity_id") == "ent-recent-1"), None)
    assert match is not None
    assert match.get("event_type") == "test.recent_tail"
    assert isinstance(match.get("payload"), dict)

    filtered = client.get(
        "/api/v1/pantheon/audit/recent?limit=5&event_type=test.recent_tail",
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert all(x.get("event_type") == "test.recent_tail" for x in filtered.json().get("items", []))


def test_pantheon_audit_append_verify_snapshot(client, auth_headers):
    # Append requires auditor role — use admin token from auth_headers.
    append = client.post(
        "/api/v1/pantheon/audit/append",
        json={
            "module": "prism_audit",
            "event_type": "test.append",
            "entity_id": "ent-1",
            "payload": {"note": "contract test"},
        },
        headers=auth_headers,
    )
    assert append.status_code == 200
    assert append.json()["success"] is True

    verify = client.get("/api/v1/pantheon/audit/verify", headers=auth_headers)
    assert verify.status_code == 200
    assert verify.json().get("valid") is True

    snap = client.post("/api/v1/pantheon/audit/snapshot", headers=auth_headers)
    assert snap.status_code == 200
    assert "root_hash" in snap.json()

    latest = client.get("/api/v1/pantheon/audit/root/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json().get("latest") is not None


def test_pantheon_access_policy_list(client, auth_headers):
    resp = client.get("/api/v1/pantheon/access-policy", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    keys = {row["policy_key"] for row in items}
    assert "pantheon.events.list" in keys
    assert "pantheon.access_policy.read" in keys
    assert "pantheon.modules.health_read" in keys
    assert "pantheon.conditions.registry_read" in keys
    assert "pantheon.taxon.receipts_read" in keys
    assert "pantheon.conditions.dry_run" in keys
    assert "pantheon.audit.recent_read" in keys


def test_pantheon_modules_health(client, auth_headers):
    resp = client.get("/api/v1/pantheon/modules/health", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total"] == 27
    assert len(data["modules"]) == 27
    assert all("health" in m and m["health"] in ("live", "standby", "planned") for m in data["modules"])
    assert "generated_at" in data
    assert "probe_ok" in data["summary"] and "probe_degraded" in data["summary"] and "probe_unknown" in data["summary"]
    for m in data["modules"]:
        pr = m.get("probe") or {}
        assert pr.get("status") in ("ok", "degraded", "unknown")
        assert "latency_ms" in pr and "detail" in pr


def test_pantheon_conditions_registry(client, auth_headers):
    resp = client.get("/api/v1/pantheon/conditions/registry", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 4
    codes = {item["code"] for item in data["items"]}
    assert "MAX_AMOUNT" in codes
    assert "RISK_SCORE" in codes
    assert "BENEFICIARY_ALLOWLIST" in codes
    assert "MIN_PAYMENT" in codes
    for item in data["items"]:
        assert item.get("implemented") is True
        assert "title" in item


def test_pantheon_conditions_dry_run(client, auth_headers):
    r = client.post(
        "/api/v1/pantheon/conditions/dry-run",
        json={"code": "MIN_PAYMENT", "payment": {"amount": 100}, "config": {"minimum": 10}},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("passed") is True
    assert body.get("code") == "MIN_PAYMENT"
    assert "eval_ms" in body

    bad = client.post(
        "/api/v1/pantheon/conditions/dry-run",
        json={"code": "MIN_PAYMENT", "payment": {"amount": 5}, "config": {"minimum": 10}},
        headers=auth_headers,
    )
    assert bad.status_code == 200
    assert bad.json().get("passed") is False


def test_pantheon_access_policy_db_enforces_min_role(client, auth_headers):
    from backend.database import db as pantheon_db

    pantheon_db.upsert_pantheon_access_policy("pantheon.events.list", "superadmin", 1, "pytest lockdown")
    try:
        denied = client.get("/api/v1/pantheon/events?limit=1", headers=auth_headers)
        assert denied.status_code == 403
    finally:
        pantheon_db.upsert_pantheon_access_policy("pantheon.events.list", "read_only", 1, "")


def test_pantheon_access_policy_put_invalid_role(client, auth_headers):
    bad = client.put(
        "/api/v1/pantheon/access-policy/pantheon.events.list",
        json={"min_role": "not_a_real_role", "enabled": True},
        headers=auth_headers,
    )
    assert bad.status_code == 400


def test_pantheon_access_policy_put_happy_path(client, auth_headers):
    key = "pantheon.events.list"
    put = client.put(
        f"/api/v1/pantheon/access-policy/{key}",
        json={"min_role": "operator", "enabled": True, "description": "pytest happy path"},
        headers=auth_headers,
    )
    assert put.status_code == 200
    body = put.json()
    assert body.get("success") is True
    assert body["policy"]["min_role"] == "operator"
    assert body["policy"]["enabled"] is True

    listed = client.get("/api/v1/pantheon/access-policy", headers=auth_headers)
    assert listed.status_code == 200
    row = next(r for r in listed.json()["items"] if r["policy_key"] == key)
    assert row["min_role"] == "operator"

    reset = client.put(
        f"/api/v1/pantheon/access-policy/{key}",
        json={"min_role": "read_only", "enabled": True, "description": ""},
        headers=auth_headers,
    )
    assert reset.status_code == 200
    assert reset.json()["policy"]["min_role"] == "read_only"
