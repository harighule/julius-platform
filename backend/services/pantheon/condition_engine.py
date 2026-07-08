from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ConditionResult:
    code: str
    passed: bool
    reason: str
    details: dict[str, Any]


class ConditionEvaluator(Protocol):
    code: str

    def evaluate(self, payment: dict[str, Any], config: dict[str, Any]) -> ConditionResult:
        ...


class MaxAmountEvaluator:
    code = "MAX_AMOUNT"

    def evaluate(self, payment: dict[str, Any], config: dict[str, Any]) -> ConditionResult:
        amount = float(payment.get("amount", 0))
        threshold = float(config.get("threshold", 0))
        passed = amount <= threshold if threshold > 0 else True
        reason = "amount within threshold" if passed else "amount exceeds threshold"
        return ConditionResult(
            code=self.code,
            passed=passed,
            reason=reason,
            details={"amount": amount, "threshold": threshold},
        )


class RiskScoreEvaluator:
    code = "RISK_SCORE"

    def evaluate(self, payment: dict[str, Any], config: dict[str, Any]) -> ConditionResult:
        score = float(payment.get("risk_score", 0.5))
        max_score = float(config.get("max_score", 1.0))
        passed = score <= max_score
        reason = "risk score accepted" if passed else "risk score too high"
        return ConditionResult(
            code=self.code,
            passed=passed,
            reason=reason,
            details={"risk_score": score, "max_score": max_score},
        )


class BeneficiaryAllowlistEvaluator:
    code = "BENEFICIARY_ALLOWLIST"

    def evaluate(self, payment: dict[str, Any], config: dict[str, Any]) -> ConditionResult:
        beneficiary_id = str(payment.get("beneficiary_id", ""))
        allowlist = [str(x) for x in config.get("allowlist", [])]
        if not allowlist:
            return ConditionResult(
                code=self.code,
                passed=True,
                reason="allowlist not configured",
                details={"beneficiary_id": beneficiary_id},
            )
        passed = beneficiary_id in allowlist
        reason = "beneficiary allowed" if passed else "beneficiary not allowlisted"
        return ConditionResult(
            code=self.code,
            passed=passed,
            reason=reason,
            details={"beneficiary_id": beneficiary_id},
        )


class PantheonConditionEngine:
    def __init__(self) -> None:
        self._evaluators: dict[str, ConditionEvaluator] = {
            "MAX_AMOUNT": MaxAmountEvaluator(),
            "RISK_SCORE": RiskScoreEvaluator(),
            "BENEFICIARY_ALLOWLIST": BeneficiaryAllowlistEvaluator(),
        }

    def register_evaluator(self, evaluator: ConditionEvaluator, *, overwrite: bool = False) -> None:
        code = evaluator.code.upper()
        if code in self._evaluators and not overwrite:
            raise ValueError(f"evaluator '{code}' already registered")
        self._evaluators[code] = evaluator

    def registered_codes(self) -> set[str]:
        return set(self._evaluators.keys())

    def evaluate_single(self, code: str, payment: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        code_u = str(code or "").upper()
        cfg = config or {}
        evaluator = self._evaluators.get(code_u)
        if evaluator is None:
            return {
                "code": code_u or "UNKNOWN",
                "passed": False,
                "reason": "no evaluator registered",
                "details": {"config": cfg},
            }
        r = evaluator.evaluate(payment, cfg)
        return {
            "code": r.code,
            "passed": r.passed,
            "reason": r.reason,
            "details": r.details,
        }

    def evaluate(self, payment: dict[str, Any], conditions: list[dict[str, Any]]) -> dict[str, Any]:
        results: list[ConditionResult] = []
        for condition in conditions:
            code = str(condition.get("code", "")).upper()
            config = condition.get("config", {}) or {}
            evaluator = self._evaluators.get(code)
            if evaluator is None:
                results.append(
                    ConditionResult(
                        code=code or "UNKNOWN",
                        passed=False,
                        reason="no evaluator registered",
                        details={"config": config},
                    )
                )
                continue
            results.append(evaluator.evaluate(payment, config))

        failed = [r for r in results if not r.passed]
        status = "CLEARED" if not failed else "HELD"
        return {
            "status": status,
            "all_passed": not failed,
            "results": [
                {"code": r.code, "passed": r.passed, "reason": r.reason, "details": r.details}
                for r in results
            ],
            "failed_codes": [r.code for r in failed],
        }


condition_engine = PantheonConditionEngine()

