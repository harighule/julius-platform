"""
Runtime-registered NEXUS evaluators (startup). Safe, in-repo only — no remote code.
"""

from __future__ import annotations

from typing import Any

from .condition_engine import ConditionResult, PantheonConditionEngine, condition_engine


class MinPaymentEvaluator:
    code = "MIN_PAYMENT"

    def evaluate(self, payment: dict[str, Any], config: dict[str, Any]) -> ConditionResult:
        amt = float(payment.get("amount", payment.get("gross_amount", 0)))
        minimum = float(config.get("minimum", 0))
        if minimum <= 0:
            return ConditionResult(
                code=self.code,
                passed=True,
                reason="minimum not configured",
                details={"amount": amt, "minimum": minimum},
            )
        passed = amt >= minimum
        reason = "amount meets minimum" if passed else "amount below minimum"
        return ConditionResult(
            code=self.code,
            passed=passed,
            reason=reason,
            details={"amount": amt, "minimum": minimum},
        )


_plugins_installed = False


def ensure_nexus_evaluator_plugins(engine: PantheonConditionEngine | None = None) -> None:
    global _plugins_installed
    if _plugins_installed:
        return
    eng = engine or condition_engine
    eng.register_evaluator(MinPaymentEvaluator(), overwrite=False)
    _plugins_installed = True
