from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TaxRule:
    event_type: str
    category_code: str
    rate: float
    threshold_min: float = 0.0


RECEIPT_VERSION = 1


def tax_computation_receipt_hash(request: dict[str, Any], result: dict[str, Any]) -> str:
    """Deterministic SHA-256 over canonical request slice + compute result (excludes prior receipt_hash)."""
    result_for_hash = {k: v for k, v in result.items() if k not in ("receipt_hash", "receipt_version")}
    body = {
        "payment_id": request.get("payment_id"),
        "payment_type": str(request.get("payment_type", "")).upper(),
        "gross_amount": float(request.get("gross_amount", 0) or 0),
        "category_code": str(request.get("category_code", "DEFAULT")).upper(),
        "metadata": request.get("metadata") or {},
        "result": result_for_hash,
    }
    blob = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


DEFAULT_TAX_RULES: list[TaxRule] = [
    TaxRule(event_type="SALARY", category_code="DEFAULT", rate=0.10),
    TaxRule(event_type="VENDOR_PAYMENT", category_code="CONTRACTOR", rate=0.02),
    TaxRule(event_type="VENDOR_PAYMENT", category_code="PROF_SERVICE", rate=0.10),
    TaxRule(event_type="PROPERTY", category_code="STAMP_DUTY", rate=0.05),
]


def compute_tax(payload: dict[str, Any], rules: list[TaxRule] | None = None) -> dict[str, Any]:
    rule_set = rules or DEFAULT_TAX_RULES
    event_type = str(payload.get("payment_type", "")).upper()
    category_code = str(payload.get("category_code", "DEFAULT")).upper()
    gross_amount = float(payload.get("gross_amount", 0))

    selected = None
    for rule in rule_set:
        if rule.event_type == event_type and rule.category_code == category_code:
            selected = rule
            break
    if selected is None:
        for rule in rule_set:
            if rule.event_type == event_type and rule.category_code == "DEFAULT":
                selected = rule
                break

    if selected is None or gross_amount < selected.threshold_min:
        return {
            "taxable": False,
            "tax_amount": 0.0,
            "net_amount": gross_amount,
            "tax_type": "NONE",
            "rate_applied": 0.0,
            "remittance_account": None,
        }

    tax_amount = round(gross_amount * selected.rate, 2)
    net_amount = round(gross_amount - tax_amount, 2)
    return {
        "taxable": True,
        "tax_amount": tax_amount,
        "net_amount": net_amount,
        "tax_type": f"{selected.event_type}_WITHHOLDING",
        "rate_applied": selected.rate,
        "remittance_account": "TREASURY_TAX_ACCOUNT",
    }

