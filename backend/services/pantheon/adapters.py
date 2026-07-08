from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from ...database import db
from .event_integrity import compute_pantheon_event_integrity_hash
from .rule_engine_default import PantheonControlRuleEngine


class EventBusAdapter(Protocol):
    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        ...

    def recent(
        self,
        limit: int = 100,
        *,
        module: str | None = None,
        event_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        ...


class IdentityProviderAdapter(Protocol):
    def resolve_subject(self, authorization: str) -> dict[str, Any]:
        ...


class RuleEngineAdapter(Protocol):
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        ...


class AuditStoreAdapter(Protocol):
    def append(
        self,
        module: str,
        event_type: str,
        entity_id: str,
        payload: dict[str, Any],
        *,
        attribution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...

    def verify_chain(self) -> dict[str, Any]:
        ...


@dataclass
class AccessDecision:
    allowed: bool
    reason: str


class InProcessEventBus(EventBusAdapter):
    """Publishes through SQLite (`pantheon_events`); no separate in-process buffer."""

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        ev = dict(event)
        if not ev.get("integrity_hash"):
            ev["integrity_hash"] = compute_pantheon_event_integrity_hash(ev)
        return db.add_pantheon_event(ev)

    def recent(
        self,
        limit: int = 100,
        *,
        module: str | None = None,
        event_type: str | None = None,
        entity_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return db.get_recent_pantheon_events(limit, module=module, event_type=event_type, entity_id=entity_id)


class FortressAccessMatrix:
    ROLE_PRIORITY = {
        "read_only": 10,
        "user": 20,
        "operator": 30,
        "auditor": 40,
        "admin": 50,
        "superadmin": 60,
    }

    def enforce(self, role: str, required_role: str) -> AccessDecision:
        current = self.ROLE_PRIORITY.get((role or "").lower(), 0)
        required = self.ROLE_PRIORITY.get((required_role or "").lower(), 0)
        if current >= required:
            return AccessDecision(True, "allowed")
        return AccessDecision(False, f"role '{role}' cannot access '{required_role}' operation")


class PrismAuditStore(AuditStoreAdapter):
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def append(
        self,
        module: str,
        event_type: str,
        entity_id: str,
        payload: dict[str, Any],
        *,
        attribution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            prev_hash = db.get_last_pantheon_audit_hash()
            envelope = {
                "module": module,
                "event_type": event_type,
                "entity_id": entity_id,
                "payload": payload,
                "timestamp": int(time.time() * 1000),
                "prev_hash": prev_hash,
            }
            blob = json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
            record_hash = hashlib.sha256(blob).hexdigest()
            record: dict[str, Any] = {
                "record_id": str(uuid.uuid4()),
                **envelope,
                "record_hash": record_hash,
            }
            if attribution:
                record.update(attribution)
            db.append_pantheon_audit_record(record)
            return record

    def verify_chain(self) -> dict[str, Any]:
        with self._lock:
            records = db.get_pantheon_audit_records()
            prev_hash = "0" * 64
            for idx, record in enumerate(records, start=1):
                envelope = {
                    "module": record["module"],
                    "event_type": record["event_type"],
                    "entity_id": record["entity_id"],
                    "payload": record["payload"],
                    "timestamp": record["timestamp"],
                    "prev_hash": prev_hash,
                }
                expected = hashlib.sha256(
                    json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")
                ).hexdigest()
                if expected != record["record_hash"]:
                    return {"valid": False, "failed_at": idx}
                prev_hash = record["record_hash"]
            return {"valid": True, "records": len(records)}


event_bus = InProcessEventBus()
audit_store = PrismAuditStore()
rule_engine = PantheonControlRuleEngine()
fortress_matrix = FortressAccessMatrix()

