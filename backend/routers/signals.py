"""
STRATUM Signals Router — UK public signal collection API.

Endpoints used by SignalCollectionPanel:
  POST /api/signals/collect/uk
  GET  /api/signals/status/{job_id}
  POST /api/signals/stop/{job_id}
  GET  /api/signals/profiles
  GET  /api/signals/export/{job_id}
  GET  /api/signals/validation
  GET  /api/signals/stats
  GET  /api/signals/health
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import db
from ..services.export_pipeline import build_job_export
from ..services.uk_signal_collector import (
    DEFAULT_DOC_ALIGNED_QUERIES,
    DEFAULT_GITHUB_QUERIES,
    DEFAULT_OSM_QUERIES,
    DEFAULT_PUBLIC_SOURCE_QUERIES,
    DEFAULT_PUBLIC_SPENDING_QUERIES,
    DEFAULT_PYPI_PACKAGES,
    collector,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/signals", tags=["STRATUM Signals"])


class UKCollectionStartRequest(BaseModel):
    target_profiles: int = Field(default=100_000, ge=1, le=500_000)


def _load_profiles_for_job(job_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    profiles = collector.export_job_profiles(job_id).get("profiles", [])
    if limit is not None:
        return profiles[:limit]
    return profiles


def _status_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    source_counts = snapshot.get("source_counts") or snapshot.get("source_breakdown") or {}
    collected = int(snapshot.get("collected_profiles") or 0)
    return {
        "job_id": snapshot.get("job_id"),
        "status": snapshot.get("status"),
        "progress_percent": int(snapshot.get("progress_percent") or 0),
        "collected_profiles": collected,
        "target_profiles": int(snapshot.get("target_profiles") or 0),
        "stored_profiles": collected,
        "deduplicated_profiles": collected,
        "source_breakdown": source_counts,
        "recent_errors": snapshot.get("recent_errors") or [],
        "started_at": snapshot.get("started_at"),
        "updated_at": snapshot.get("updated_at"),
        "completed_at": snapshot.get("completed_at"),
        "stop_requested": bool(snapshot.get("stop_requested")),
        "target_reached": bool(snapshot.get("target_reached")),
        "recent_profiles": snapshot.get("recent_profiles") or [],
        "per_source_cap": int(snapshot.get("per_source_cap") or 0),
    }


@router.post("/collect/uk")
async def start_uk_collection(req: UKCollectionStartRequest) -> dict[str, Any]:
    """Start UK signal collection (uksig-* job ids, profiles tagged in DB)."""
    try:
        job = await collector.start_collection(
            target_profiles=req.target_profiles,
            github_queries=list(DEFAULT_GITHUB_QUERIES),
            gitlab_queries=list(DEFAULT_PUBLIC_SOURCE_QUERIES),
            npm_queries=list(DEFAULT_PUBLIC_SOURCE_QUERIES),
            pypi_packages=list(DEFAULT_PYPI_PACKAGES),
            govuk_queries=list(DEFAULT_PUBLIC_SOURCE_QUERIES),
            spending_queries=list(DEFAULT_PUBLIC_SPENDING_QUERIES),
            gdelt_queries=list(DEFAULT_DOC_ALIGNED_QUERIES),
            osm_queries=list(DEFAULT_OSM_QUERIES),
        )
        return {
            "success": True,
            "job_id": job.job_id,
            "status": job.status,
            "target_profiles": job.target_profiles,
            "started_at": job.started_at,
            "message": (
                f"Collection started, targeting {req.target_profiles:,} profiles "
                f"(~{max(1, (req.target_profiles + 7) // 8)} per source)"
            ),
        }
    except Exception as e:
        logger.error("Collection start failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{job_id}")
async def get_status(job_id: str) -> dict[str, Any]:
    snapshot = collector.get_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return _status_payload(snapshot)


@router.post("/stop/{job_id}")
async def stop_collection(job_id: str) -> dict[str, Any]:
    job = await collector.stop_collection(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or not running")
    return {"success": True, "job_id": job_id, "message": "Stop requested"}


@router.get("/profiles")
async def list_profiles(
    limit: int = Query(100, ge=1, le=1000),
    job_id: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
) -> dict[str, Any]:
    try:
        if job_id:
            profiles = _load_profiles_for_job(job_id, limit=limit)
        else:
            conn = db._connect()
            rows = conn.execute(
                """
                SELECT extra FROM identities
                WHERE extra IS NOT NULL AND extra LIKE '%"stratum_id"%'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            conn.close()
            profiles = []
            for row in rows:
                try:
                    p = json.loads(row["extra"] or "{}")
                    if p.get("stratum_id"):
                        profiles.append(p)
                except (json.JSONDecodeError, TypeError):
                    continue

        if source:
            profiles = [
                p
                for p in profiles
                if (p.get("metadata") or {}).get("source") == source
                or source in str((p.get("metadata") or {}).get("source", ""))
            ]

        return {"count": len(profiles), "profiles": profiles}
    except Exception as e:
        logger.error("Profile listing failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/{job_id}")
async def export_collection(job_id: str) -> dict[str, Any]:
    snapshot = collector.get_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    raw_profiles = _load_profiles_for_job(job_id)
    if not raw_profiles:
        raise HTTPException(
            status_code=404,
            detail=f"No profiles collected yet for job {job_id}. Wait for collection to finish or start a new job.",
        )

    return build_job_export(raw_profiles, job_id=job_id, input_profile_count=len(raw_profiles))


@router.get("/validation")
async def get_validation_report(
    job_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict[str, Any]:
    try:
        if job_id:
            profiles = _load_profiles_for_job(job_id, limit=limit)
        else:
            conn = db._connect()
            rows = conn.execute(
                """
                SELECT extra FROM identities
                WHERE extra IS NOT NULL AND extra LIKE '%"stratum_id"%'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            conn.close()
            profiles = []
            for row in rows:
                try:
                    p = json.loads(row["extra"] or "{}")
                    if p.get("stratum_id"):
                        profiles.append(p)
                except (json.JSONDecodeError, TypeError):
                    continue

        if not profiles:
            raise HTTPException(status_code=404, detail="No profiles found")

        report = validate_batch(profiles)
        return {
            "job_id": job_id or "all",
            "profiles_checked": report.profiles_checked,
            "valid_profiles": report.valid_profiles,
            "invalid_profiles": report.invalid_profiles,
            "validation_rate": report.validation_rate,
            "total_errors": report.total_errors,
            "total_warnings": report.total_warnings,
            "synthetic_detected": report.synthetic_detected,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Validation report failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_collection_statistics() -> dict[str, Any]:
    jobs = collector.list_jobs()
    total_profiles = sum(int(j.collected_profiles) for j in jobs)
    return {
        "total_profiles_collected": total_profiles,
        "total_jobs": len(jobs),
        "completed_jobs": sum(1 for j in jobs if j.status == "completed"),
        "running_jobs": sum(1 for j in jobs if j.status == "running"),
        "failed_jobs": sum(1 for j in jobs if j.status == "failed"),
        "stopped_jobs": sum(1 for j in jobs if j.status == "stopped"),
    }


@router.get("/health")
async def health_check() -> dict[str, Any]:
    jobs = collector.list_jobs()
    return {
        "status": "ok",
        "service": "STRATUM UK Signal Collector",
        "jobs_active": sum(1 for j in jobs if j.status == "running"),
        "jobs_total": len(jobs),
    }
