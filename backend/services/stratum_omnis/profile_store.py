"""Shared STRATUM profile access helpers."""

from __future__ import annotations

import json
from typing import Any

from ...database import db


def load_stratum_profiles(limit: int | None = None) -> list[dict[str, Any]]:
    conn = db._connect()
    sql = """SELECT extra
             FROM identities
             WHERE extra IS NOT NULL AND extra LIKE '%"stratum_id"%'
             ORDER BY created_at DESC"""
    if limit is not None:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()
    conn.close()

    profiles: list[dict[str, Any]] = []
    for row in rows:
        try:
            profiles.append(json.loads(row["extra"] or "{}"))
        except (TypeError, json.JSONDecodeError):
            continue
    return profiles


def source_breakdown(profiles: list[dict[str, Any]]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for profile in profiles:
        metadata = profile.get("metadata") or {}
        source = str(metadata.get("source") or "unknown")
        breakdown[source] = breakdown.get(source, 0) + 1
    return breakdown
