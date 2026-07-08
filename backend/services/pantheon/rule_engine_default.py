"""Default Pantheon publish rule engine — explicit allow/deny with stable outcomes."""

from __future__ import annotations

import json
from typing import Any

from .contracts import MODULE_CONTRACTS

_MAX_MODULE_LEN = 128
_MAX_EVENT_TYPE_LEN = 256
_MAX_ENTITY_ID_LEN = 512
_MAX_PAYLOAD_JSON_BYTES = 65536

_ALLOWED_MODULES = frozenset(m.module_id for m in MODULE_CONTRACTS)


class PantheonControlRuleEngine:
    def evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        event = context.get("event")
        if not isinstance(event, dict):
            return {
                "passed": False,
                "reason": "rule context missing event",
                "rule_hits": ["missing_event"],
                "subject": context.get("subject"),
            }

        hits: list[str] = []
        module = str(event.get("module", ""))
        event_type = str(event.get("event_type", ""))
        entity_id = str(event.get("entity_id", ""))

        if len(module) > _MAX_MODULE_LEN or len(event_type) > _MAX_EVENT_TYPE_LEN or len(entity_id) > _MAX_ENTITY_ID_LEN:
            hits.append("field_length")
            return {
                "passed": False,
                "reason": "module, event_type, or entity_id exceeds max length",
                "rule_hits": hits,
                "subject": context.get("subject"),
            }

        if module not in _ALLOWED_MODULES:
            hits.append("unknown_module")
            return {
                "passed": False,
                "reason": f"module '{module}' is not in the Pantheon contract registry",
                "rule_hits": hits,
                "subject": context.get("subject"),
            }

        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            hits.append("payload_type")
            return {
                "passed": False,
                "reason": "payload must be an object",
                "rule_hits": hits,
                "subject": context.get("subject"),
            }

        try:
            raw = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8")
        except (TypeError, ValueError):
            hits.append("payload_json")
            return {
                "passed": False,
                "reason": "payload is not JSON-serializable",
                "rule_hits": hits,
                "subject": context.get("subject"),
            }

        if len(raw) > _MAX_PAYLOAD_JSON_BYTES:
            hits.append("payload_size")
            return {
                "passed": False,
                "reason": f"payload JSON exceeds {_MAX_PAYLOAD_JSON_BYTES} bytes",
                "rule_hits": hits,
                "subject": context.get("subject"),
            }

        return {
            "passed": True,
            "reason": "control rules satisfied",
            "rule_hits": hits,
            "subject": context.get("subject"),
        }
