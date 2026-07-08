"""Model-hub style registry and outputs for safe STRATUM modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .csie import get_csie_engine_status, get_csie_snapshot
from .feature_store import get_feature_store_snapshot
from .oracle import get_oracle_snapshot


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_model_hub_snapshot(feature_limit: int = 12, oracle_limit: int = 8, csie_limit: int = 8) -> dict[str, Any]:
    feature_store = get_feature_store_snapshot(feature_limit)
    oracle = get_oracle_snapshot(oracle_limit)
    csie = get_csie_snapshot(csie_limit)

    registry = [
        {
            "model_id": "stratum.feature_store.v1",
            "family": "feature_store",
            "status": "implemented",
            "records": feature_store["count"],
        },
        {
            "model_id": "stratum.oracle.v1",
            "family": "oracle",
            "status": "implemented",
            "records": oracle["count"],
        },
        {
            "model_id": "stratum.csie.v1",
            "family": "semantic_reasoning",
            "status": "implemented",
            "records": csie["count"],
            "engine": get_csie_engine_status(),
        },
    ]

    return {
        "generated_at": _utcnow(),
        "registry": registry,
        "feature_store_summary": feature_store["summary"],
        "oracle_preview": oracle["predictions"][:5],
        "csie_preview": csie["classifications"][:5],
    }
