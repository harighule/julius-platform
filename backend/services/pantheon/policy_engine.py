"""
JULIUS — Pantheon Policy Engine
================================
Provides policy enforcement checks before executing AttackDetector defence
actions and logs all decisions to the Pantheon audit trail.

Design
------
* ``PolicyEngine.check_defence_action()`` runs before any blacklist, rotation,
  or escalation action is executed, ensuring a consistent governance gate.
* All decisions (allowed or denied) are logged via the Pantheon audit adapter.
* Policies are configurable: default is ``allow_all`` for the MVP; production
  deployments can swap in a stricter rule set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Policy result
# ---------------------------------------------------------------------------


class PolicyResult:
    """Result of a policy evaluation."""

    def __init__(
        self,
        allowed: bool,
        reason: str = "",
        policy_name: str = "default",
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.policy_name = policy_name
        self.evaluated_at = datetime.now(tz=timezone.utc)

    def __repr__(self) -> str:
        return (
            f"PolicyResult(allowed={self.allowed}, policy={self.policy_name!r}, "
            f"reason={self.reason!r})"
        )


# ---------------------------------------------------------------------------
# Built-in policy rules
# ---------------------------------------------------------------------------


def _policy_allow_all(action_type: str, context: Dict) -> PolicyResult:
    """Default policy: allow all defence actions (MVP)."""
    return PolicyResult(allowed=True, reason="allow_all policy", policy_name="allow_all")


def _policy_no_auto_blacklist(action_type: str, context: Dict) -> PolicyResult:
    """Conservative policy: disallow automatic blacklisting without human approval."""
    if action_type == "blacklist_node":
        return PolicyResult(
            allowed=False,
            reason="Blacklist actions require human approval under no_auto_blacklist policy",
            policy_name="no_auto_blacklist",
        )
    return PolicyResult(
        allowed=True,
        reason="action type does not require human approval",
        policy_name="no_auto_blacklist",
    )


def _policy_critical_only(action_type: str, context: Dict) -> PolicyResult:
    """Strict policy: only allow auto-response for critical severity alerts."""
    severity = context.get("severity", "low")
    if severity == "critical":
        return PolicyResult(
            allowed=True,
            reason="critical severity — auto-response permitted",
            policy_name="critical_only",
        )
    return PolicyResult(
        allowed=False,
        reason=f"Severity '{severity}' is below critical — auto-response denied",
        policy_name="critical_only",
    )


# ---------------------------------------------------------------------------
# PolicyEngine
# ---------------------------------------------------------------------------


BUILT_IN_POLICIES = {
    "allow_all": _policy_allow_all,
    "no_auto_blacklist": _policy_no_auto_blacklist,
    "critical_only": _policy_critical_only,
}


class PolicyEngine:
    """
    Governance gate for all AttackDetector defence actions.

    The engine evaluates the configured policy before any action is executed
    and logs every decision to the Pantheon audit trail.

    Usage::

        engine = PolicyEngine(policy_name="allow_all")
        result = engine.check_defence_action(
            action_type="blacklist_node",
            alert_id="abc-123",
            context={"severity": "critical", "node_ids": ["evil-1"]},
        )
        if result.allowed:
            ...execute action...
    """

    def __init__(self, policy_name: str = "allow_all") -> None:
        self.policy_name = policy_name
        self._policy_fn = BUILT_IN_POLICIES.get(policy_name, _policy_allow_all)
        logger.info("PolicyEngine initialised with policy '%s'", policy_name)

    def check_defence_action(
        self,
        action_type: str,
        alert_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> PolicyResult:
        """
        Evaluate whether a defence action is permitted.

        Parameters
        ----------
        action_type:
            The type of defence action (e.g. ``"blacklist_node"``).
        alert_id:
            ID of the alert that triggered the action.
        context:
            Additional metadata (severity, node_ids, etc.) for policy evaluation.

        Returns
        -------
        PolicyResult
            ``result.allowed`` is True if the action should proceed.
        """
        ctx = context or {}
        result = self._policy_fn(action_type, ctx)

        self._audit_log(action_type, alert_id, ctx, result)

        if result.allowed:
            logger.debug(
                "PolicyEngine ALLOW | action=%s alert=%s policy=%s",
                action_type, alert_id, result.policy_name,
            )
        else:
            logger.warning(
                "PolicyEngine DENY | action=%s alert=%s policy=%s reason=%s",
                action_type, alert_id, result.policy_name, result.reason,
            )

        return result

    def _audit_log(
        self,
        action_type: str,
        alert_id: str,
        context: Dict,
        result: PolicyResult,
    ) -> None:
        """Persist the policy decision to the Pantheon audit trail (best-effort)."""
        try:
            from ..client import pantheon_client  # type: ignore

            pantheon_client.record_event(
                event_type="policy_engine_decision",
                data={
                    "action_type": action_type,
                    "alert_id": alert_id,
                    "policy_name": result.policy_name,
                    "allowed": result.allowed,
                    "reason": result.reason,
                    "evaluated_at": result.evaluated_at.isoformat(),
                    "context": {k: str(v) for k, v in context.items()},
                },
            )
        except Exception as exc:
            logger.debug("Pantheon audit log skipped: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton (default: allow_all for MVP)
# ---------------------------------------------------------------------------

import os as _os

_POLICY_NAME = _os.getenv("VEIL_POLICY_ENGINE", "allow_all")
policy_engine = PolicyEngine(policy_name=_POLICY_NAME)
