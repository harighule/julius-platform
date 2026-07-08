"""
PANTHEON control-plane router for incremental integration.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ..database import db
from ..services.pantheon.adapters import audit_store, event_bus, fortress_matrix, rule_engine
from ..services.pantheon.condition_engine import condition_engine
from ..services.pantheon.condition_registry import list_nexus_condition_registry
from ..services.pantheon.contracts import MODULE_CONTRACTS, PantheonModuleContract, list_module_contracts
from ..services.pantheon.module_health import build_modules_health_snapshot
from ..services.pantheon.nexus_plugins import ensure_nexus_evaluator_plugins
from ..services.pantheon.event_integrity import compute_pantheon_event_integrity_hash
from ..services.pantheon.taxon import RECEIPT_VERSION, compute_tax, tax_computation_receipt_hash
from ..services.pantheon.audit_jobs import run_audit_snapshot_cycle
from ..services.pantheon.rate_limit import enforce_pantheon_mutation_rate

ensure_nexus_evaluator_plugins()

_MAX_CONDITION_DRY_RUN_SEC = 0.25

router = APIRouter(prefix="/api/v1/pantheon", tags=["Pantheon"])

_VALID_POLICY_ROLES = frozenset(
    {"read_only", "user", "operator", "auditor", "admin", "superadmin"}
)


class PantheonEventIn(BaseModel):
    module: str
    event_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    idempotency_key: str | None = None


class EventIntegrityBatchIn(BaseModel):
    event_ids: list[str] = Field(default_factory=list)


class AuditRecordIn(BaseModel):
    module: str
    event_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ConditionEvaluationIn(BaseModel):
    payment: dict[str, Any]
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str | None = None


class ConditionDryRunIn(BaseModel):
    code: str
    payment: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class TaxComputeIn(BaseModel):
    payment_id: str
    payment_type: str
    gross_amount: float
    category_code: str = "DEFAULT"
    metadata: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class AccessPolicyPutIn(BaseModel):
    min_role: str
    enabled: bool = True
    description: str = ""


def _require_subject(authorization: str) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    result = db.verify_jwt_token(token)
    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid token"))
    return result


def _require_role(subject: dict[str, Any], required_role: str) -> None:
    decision = fortress_matrix.enforce(subject.get("role", ""), required_role)
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)


def _require_pantheon_policy(subject: dict[str, Any], policy_key: str, fallback_min_role: str) -> None:
    configured = db.get_pantheon_policy_min_role(policy_key)
    min_role = (configured or fallback_min_role).lower()
    _require_role(subject, min_role)


def _enforce_publish_rules(event: dict[str, Any], subject_username: str | None) -> dict[str, Any]:
    decision = rule_engine.evaluate({"event": event, "subject": subject_username})
    if not decision.get("passed"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "pantheon_rule_engine_denied",
                "reason": decision.get("reason", "denied"),
                "rule_hits": decision.get("rule_hits", []),
            },
        )
    return decision


def _pantheon_attribution(subject: dict[str, Any], request: Request | None) -> dict[str, Any]:
    """HTTP + JWT metadata persisted with Pantheon writes (not part of PRISM hash preimage)."""
    host = ""
    ua = ""
    if request is not None:
        if request.client and request.client.host:
            host = request.client.host
        ua = (request.headers.get("user-agent") or "")[:500]
    claims = {
        "user_id": subject.get("user_id"),
        "username": subject.get("username"),
        "role": subject.get("role"),
    }
    return {
        "actor_user_id": subject.get("user_id"),
        "actor_username": subject.get("username"),
        "actor_role": subject.get("role"),
        "client_ip": host or None,
        "user_agent": ua or None,
        "subject_claims_json": json.dumps(claims, separators=(",", ":"), sort_keys=True),
    }


@router.get("/modules")
async def pantheon_modules() -> dict[str, Any]:
    return {
        "items": list_module_contracts(),
        "count": len(MODULE_CONTRACTS),
    }


@router.get("/modules/health")
async def pantheon_modules_health(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.modules.health_read", "read_only")
    return await build_modules_health_snapshot()


@router.get("/modules/{module_id}")
async def pantheon_module_detail(module_id: str) -> dict[str, Any]:
    module = next((m for m in MODULE_CONTRACTS if m.module_id == module_id), None)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Unknown module '{module_id}'")
    enabled = os.getenv(module.feature_flag, "0") == "1"
    return {
        "module_id": module.module_id,
        "name": module.name,
        "tier": module.tier,
        "status": module.status,
        "feature_flag": module.feature_flag,
        "enabled": enabled,
    }


@router.get("/registry/status")
async def pantheon_registry_status() -> dict[str, Any]:
    statuses = []
    for module in MODULE_CONTRACTS:
        statuses.append(
            {
                "module_id": module.module_id,
                "name": module.name,
                "status": module.status,
                "enabled": os.getenv(module.feature_flag, "0") == "1",
                "feature_flag": module.feature_flag,
            }
        )
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "modules": statuses}


@router.get("/access-policy")
async def list_access_policy(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.access_policy.read", "read_only")
    return {"items": db.list_pantheon_access_policies()}


@router.put("/access-policy/{policy_key:path}")
async def put_access_policy(
    policy_key: str,
    payload: AccessPolicyPutIn,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.access_policy.write", "admin")
    enforce_pantheon_mutation_rate(subject.get("user_id"), "access_policy.put")
    role = (payload.min_role or "").lower()
    if role not in _VALID_POLICY_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid min_role '{payload.min_role}'")
    updated = db.upsert_pantheon_access_policy(
        policy_key,
        role,
        1 if payload.enabled else 0,
        payload.description,
    )
    return {"success": True, "policy": updated}


@router.post("/events")
async def publish_event(
    payload: PantheonEventIn,
    request: Request,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.events.publish", "operator")
    idem_key = payload.idempotency_key or f"idem-{uuid.uuid4().hex}"
    existing = db.get_pantheon_event_by_idempotency_key(idem_key)
    if existing:
        return {"success": True, "idempotent_replay": True, "event": existing}
    enforce_pantheon_mutation_rate(subject.get("user_id"), "events.publish")
    envelope = {
        "event_id": str(uuid.uuid4()),
        "module": payload.module,
        "event_type": payload.event_type,
        "entity_id": payload.entity_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": payload.trace_id or f"trace-{uuid.uuid4().hex}",
        "payload": payload.payload,
        "idempotency_key": idem_key,
        "integrity_hash": "",
        **_pantheon_attribution(subject, request),
    }
    _enforce_publish_rules(envelope, subject.get("username"))
    stored = event_bus.publish(envelope)
    return {"success": True, "event": stored}


@router.get("/events")
async def recent_events(
    limit: int = 100,
    module: str | None = None,
    event_type: str | None = None,
    entity_id: str | None = None,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.events.list", "read_only")
    safe_limit = min(max(limit, 1), 500)
    items = event_bus.recent(
        safe_limit,
        module=module,
        event_type=event_type,
        entity_id=entity_id,
    )
    return {"items": items, "count": len(items), "limit": safe_limit}


@router.post("/events/verify-integrity")
async def verify_pantheon_events_integrity_batch(
    payload: EventIntegrityBatchIn,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    """Check up to 50 events in one round-trip (same policy as ``GET /events``)."""
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.events.list", "read_only")
    raw = [str(x).strip() for x in payload.event_ids if str(x).strip()]
    if len(raw) > 50:
        raise HTTPException(status_code=400, detail="at most 50 event_ids allowed")
    seen: set[str] = set()
    event_ids: list[str] = []
    for x in raw:
        if x not in seen:
            seen.add(x)
            event_ids.append(x)
    items: list[dict[str, Any]] = []
    for eid in event_ids:
        row = db.get_pantheon_event_by_event_id(eid)
        if not row:
            items.append({"event_id": eid, "integrity_valid": False, "reason": "not_found"})
            continue
        stored = (row.get("integrity_hash") or "").strip()
        computed = compute_pantheon_event_integrity_hash(row)
        valid = bool(stored) and stored == computed
        items.append(
            {
                "event_id": eid,
                "integrity_valid": valid,
                "stored_hash": stored or None,
                "computed_hash": computed,
            }
        )
    return {"items": items, "count": len(items)}


@router.get("/events/{event_id}/integrity")
async def verify_pantheon_event_integrity(event_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
    """Recompute SHA-256 from stored fields and compare to ``integrity_hash`` (same policy as event list)."""
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.events.list", "read_only")
    row = db.get_pantheon_event_by_event_id(event_id)
    if not row:
        raise HTTPException(status_code=404, detail="event not found")
    stored = (row.get("integrity_hash") or "").strip()
    computed = compute_pantheon_event_integrity_hash(row)
    valid = bool(stored) and stored == computed
    return {
        "event_id": event_id,
        "integrity_valid": valid,
        "stored_hash": stored or None,
        "computed_hash": computed,
    }


@router.get("/events/{event_id}")
async def get_pantheon_event(event_id: str, authorization: str = Header(default="")) -> dict[str, Any]:
    """Return one durable event row (same policy as list / integrity)."""
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.events.list", "read_only")
    row = db.get_pantheon_event_by_event_id(event_id)
    if not row:
        raise HTTPException(status_code=404, detail="event not found")
    return {"event": row}


@router.post("/audit/append")
async def append_audit_record(
    payload: AuditRecordIn,
    request: Request,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.audit.append", "auditor")
    enforce_pantheon_mutation_rate(subject.get("user_id"), "audit.append")
    record = audit_store.append(
        module=payload.module,
        event_type=payload.event_type,
        entity_id=payload.entity_id,
        payload=payload.payload,
        attribution=_pantheon_attribution(subject, request),
    )
    return {"success": True, "record": record}


@router.get("/audit/verify")
async def verify_audit_chain(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.audit.verify", "auditor")
    return audit_store.verify_chain()


@router.post("/audit/snapshot")
async def snapshot_audit_root(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.audit.snapshot", "auditor")
    enforce_pantheon_mutation_rate(subject.get("user_id"), "audit.snapshot")
    return run_audit_snapshot_cycle()


@router.get("/audit/root/latest")
async def latest_audit_root(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.audit.root_latest", "read_only")
    latest = db.get_latest_pantheon_audit_root()
    return {"latest": latest}


@router.get("/audit/recent")
async def audit_recent(
    limit: int = 30,
    event_type: str | None = None,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.audit.recent_read", "auditor")
    safe = min(max(limit, 1), 200)
    et = (event_type or "").strip() or None
    items = db.get_recent_pantheon_audit_entries(safe, event_type=et)
    return {"count": len(items), "items": items}


@router.get("/conditions/registry")
async def nexus_conditions_registry(authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.conditions.registry_read", "read_only")
    items = list_nexus_condition_registry(condition_engine)
    return {"count": len(items), "items": items}


@router.post("/conditions/dry-run")
async def conditions_dry_run(
    payload: ConditionDryRunIn,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.conditions.dry_run", "auditor")

    def _run() -> dict[str, Any]:
        return condition_engine.evaluate_single(payload.code, payload.payment, payload.config)

    t0 = time.perf_counter()
    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_run), timeout=_MAX_CONDITION_DRY_RUN_SEC)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="condition dry-run timed out") from None
    eval_ms = (time.perf_counter() - t0) * 1000
    return {**raw, "eval_ms": round(eval_ms, 3)}


@router.post("/conditions/evaluate")
async def evaluate_conditions(
    payload: ConditionEvaluationIn,
    request: Request,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.conditions.evaluate", "operator")
    idem_key = payload.idempotency_key or f"idem-{uuid.uuid4().hex}"
    existing = db.get_pantheon_event_by_idempotency_key(idem_key)
    if existing:
        return {
            "status": existing.get("payload", {}).get("status", "HELD"),
            "all_passed": existing.get("payload", {}).get("all_passed", False),
            "results": existing.get("payload", {}).get("results", []),
            "failed_codes": existing.get("payload", {}).get("failed_codes", []),
            "idempotent_replay": True,
        }
    enforce_pantheon_mutation_rate(subject.get("user_id"), "conditions.evaluate")
    result = condition_engine.evaluate(payload.payment, payload.conditions)
    env = {
        "event_id": str(uuid.uuid4()),
        "module": "nexus_gate",
        "event_type": "conditions.evaluated",
        "entity_id": str(payload.payment.get("payment_id", "unknown")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": f"trace-{uuid.uuid4().hex}",
        "payload": result,
        "idempotency_key": idem_key,
        "integrity_hash": "",
        **_pantheon_attribution(subject, request),
    }
    _enforce_publish_rules(env, subject.get("username"))
    event_bus.publish(env)
    return result


@router.get("/taxon/receipts")
async def taxon_receipts(limit: int = 50, authorization: str = Header(default="")) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.taxon.receipts_read", "read_only")
    safe = min(max(limit, 1), 200)
    rows = db.get_pantheon_taxon_receipt_events(safe)
    items: list[dict[str, Any]] = []
    for r in rows:
        pl = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        res = pl.get("result") if isinstance(pl.get("result"), dict) else {}
        items.append(
            {
                "event_id": r.get("event_id"),
                "payment_id": r.get("entity_id"),
                "timestamp": r.get("timestamp"),
                "trace_id": r.get("trace_id"),
                "idempotency_key": r.get("idempotency_key"),
                "receipt_hash": res.get("receipt_hash"),
                "receipt_version": res.get("receipt_version"),
                "taxable": res.get("taxable"),
                "tax_amount": res.get("tax_amount"),
            }
        )
    return {"count": len(items), "items": items}


@router.post("/taxon/compute")
async def taxon_compute(
    payload: TaxComputeIn,
    request: Request,
    authorization: str = Header(default=""),
) -> dict[str, Any]:
    subject = _require_subject(authorization)
    _require_pantheon_policy(subject, "pantheon.taxon.compute", "operator")
    idem_key = payload.idempotency_key or f"idem-{uuid.uuid4().hex}"
    existing = db.get_pantheon_event_by_idempotency_key(idem_key)
    if existing:
        prior = existing.get("payload", {}).get("result")
        if isinstance(prior, dict):
            return {**prior, "idempotent_replay": True}
    enforce_pantheon_mutation_rate(subject.get("user_id"), "taxon.compute")
    req_dump = payload.model_dump()
    result = compute_tax(req_dump)
    receipt_hash = tax_computation_receipt_hash(req_dump, result)
    result_with_receipt = {**result, "receipt_hash": receipt_hash, "receipt_version": RECEIPT_VERSION}
    envelope = {
        "event_id": str(uuid.uuid4()),
        "module": "taxon",
        "event_type": "tax.computed",
        "entity_id": payload.payment_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": f"trace-{uuid.uuid4().hex}",
        "payload": {"request": req_dump, "result": result_with_receipt},
        "idempotency_key": idem_key,
        "integrity_hash": "",
        **_pantheon_attribution(subject, request),
    }
    _enforce_publish_rules(envelope, subject.get("username"))
    stored = event_bus.publish(envelope)
    attr = _pantheon_attribution(subject, request)
    try:
        audit_store.append(
            module="prism_audit",
            event_type="taxon.receipt.mirror",
            entity_id=payload.payment_id,
            payload={
                "receipt_hash": result_with_receipt.get("receipt_hash"),
                "receipt_version": result_with_receipt.get("receipt_version"),
                "source_event_id": stored.get("event_id"),
                "idempotency_key": idem_key,
            },
            attribution=attr,
        )
    except Exception:
        pass
    return result_with_receipt

