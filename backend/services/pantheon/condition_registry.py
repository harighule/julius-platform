"""
NEXUS condition code catalog — metadata for built-ins plus merge with engine-registered evaluators (PR-4).
"""

from __future__ import annotations

from typing import Any

# Stable catalog for operators / UI; keys must match evaluator `code` values.
CONDITION_CODE_CATALOG: dict[str, dict[str, Any]] = {
    "MAX_AMOUNT": {
        "title": "Maximum amount",
        "description": "Payment amount must not exceed a configured threshold.",
        "config_keys": ["threshold"],
    },
    "RISK_SCORE": {
        "title": "Risk score ceiling",
        "description": "Payment risk score must stay at or below a maximum.",
        "config_keys": ["max_score"],
    },
    "BENEFICIARY_ALLOWLIST": {
        "title": "Beneficiary allowlist",
        "description": "Beneficiary id must appear in the configured allowlist (empty allowlist passes).",
        "config_keys": ["allowlist"],
    },
    "MIN_PAYMENT": {
        "title": "Minimum payment",
        "description": "Payment amount must be at least a configured minimum (zero minimum passes).",
        "config_keys": ["minimum"],
    },
}


def list_nexus_condition_registry(engine: Any) -> list[dict[str, Any]]:
    """Merge catalog entries with any extra evaluators registered only on the engine."""
    registered = engine.registered_codes()
    codes = set(CONDITION_CODE_CATALOG) | registered
    items: list[dict[str, Any]] = []
    for code in sorted(codes):
        meta = CONDITION_CODE_CATALOG.get(code, {})
        items.append(
            {
                "code": code,
                "title": meta.get("title", code),
                "description": meta.get("description", ""),
                "config_keys": list(meta.get("config_keys", [])),
                "implemented": code in registered,
                "catalogued": code in CONDITION_CODE_CATALOG,
            }
        )
    return items
