"""
PR-4 module health: lightweight probes with per-module timeouts (SQLite + key modules).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ...database import db
from .contracts import MODULE_CONTRACTS, PantheonModuleContract

PROBE_TIMEOUT_SEC = 0.35


def _legacy_health_facet(module: PantheonModuleContract, enabled: bool) -> str:
    if enabled:
        return "live"
    if module.status == "planned":
        return "planned"
    return "standby"


def _probe_sqlite_events() -> tuple[str, str]:
    db.get_recent_pantheon_events(1)
    return "ok", "sqlite pantheon_events"


def _probe_nexus_gate() -> tuple[str, str]:
    from .condition_engine import condition_engine

    r = condition_engine.evaluate({"payment_id": "_probe", "amount": 0}, [])
    if r.get("status") == "CLEARED" and r.get("all_passed"):
        return "ok", "nexus evaluate"
    return "degraded", "unexpected nexus response"


def _probe_taxon() -> tuple[str, str]:
    from .taxon import compute_tax

    out = compute_tax(
        {
            "payment_id": "__health__",
            "payment_type": "VENDOR_PAYMENT",
            "gross_amount": 1.0,
            "category_code": "DEFAULT",
            "metadata": {},
        }
    )
    if "tax_amount" in out:
        return "ok", "taxon compute"
    return "degraded", "missing tax_amount"


def _probe_prism_chain() -> tuple[str, str]:
    db.get_last_pantheon_audit_hash()
    return "ok", "audit chain readable"


_MODULE_PROBES: dict[str, Callable[[], tuple[str, str]]] = {
    "nexus_gate": _probe_nexus_gate,
    "taxon": _probe_taxon,
    "prism_audit": _probe_prism_chain,
}


async def _timed_probe(fn: Callable[[], tuple[str, str]]) -> tuple[str, str, float]:
    t0 = time.perf_counter()
    try:
        status, detail = await asyncio.wait_for(asyncio.to_thread(fn), timeout=PROBE_TIMEOUT_SEC)
        ms = (time.perf_counter() - t0) * 1000
        return status, detail, ms
    except TimeoutError:
        ms = (time.perf_counter() - t0) * 1000
        return "degraded", "probe timeout", ms
    except Exception as e:
        ms = (time.perf_counter() - t0) * 1000
        return "degraded", str(e)[:160], ms


async def _probe_one_module(module: PantheonModuleContract, enabled: bool) -> dict[str, Any]:
    facet = _legacy_health_facet(module, enabled)
    row: dict[str, Any] = {
        "module_id": module.module_id,
        "name": module.name,
        "tier": module.tier,
        "contract_status": module.status,
        "feature_flag": module.feature_flag,
        "enabled": enabled,
        "health": facet,
    }
    if not enabled:
        row["probe"] = {
            "status": "unknown",
            "latency_ms": 0.0,
            "detail": "feature flag disabled",
        }
        return row

    fn = _MODULE_PROBES.get(module.module_id, _probe_sqlite_events)
    status, detail, ms = await _timed_probe(fn)
    row["probe"] = {
        "status": status,
        "latency_ms": round(ms, 3),
        "detail": detail,
    }
    return row


async def build_modules_health_snapshot() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    tasks = [
        _probe_one_module(m, os.getenv(m.feature_flag, "0") == "1") for m in MODULE_CONTRACTS
    ]
    modules = await asyncio.gather(*tasks)

    summary = {
        "live": sum(1 for x in modules if x["health"] == "live"),
        "standby": sum(1 for x in modules if x["health"] == "standby"),
        "planned": sum(1 for x in modules if x["health"] == "planned"),
        "total": len(modules),
        "probe_ok": sum(1 for x in modules if x.get("probe", {}).get("status") == "ok"),
        "probe_degraded": sum(1 for x in modules if x.get("probe", {}).get("status") == "degraded"),
        "probe_unknown": sum(1 for x in modules if x.get("probe", {}).get("status") == "unknown"),
    }
    return {
        "generated_at": generated_at,
        "summary": summary,
        "modules": modules,
    }
