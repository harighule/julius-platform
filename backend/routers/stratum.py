"""STRATUM OMNIS architecture router."""

from fastapi import APIRouter

from ..services.stratum_omnis import (
    get_csie_snapshot,
    get_feature_store_snapshot,
    get_identity_resolution_snapshot,
    get_model_hub_snapshot,
    get_oracle_snapshot,
    get_stratum_blueprint,
    get_stratum_runtime,
    get_stream_processing_snapshot,
)
from ..services.causal_functor import get_causal_functor_diagnostics

router = APIRouter(prefix="/api/stratum", tags=["STRATUM"])


@router.get("/blueprint")
async def stratum_blueprint():
    return get_stratum_blueprint()


@router.get("/runtime")
async def stratum_runtime():
    return get_stratum_runtime()


@router.get("/feature-store")
async def stratum_feature_store(limit: int = 25):
    return get_feature_store_snapshot(limit=max(1, min(limit, 100)))


@router.get("/stream-processing")
async def stratum_stream_processing(limit: int = 50):
    return get_stream_processing_snapshot(limit=max(1, min(limit, 200)))


@router.get("/identity-resolution")
async def stratum_identity_resolution(limit: int = 100):
    return get_identity_resolution_snapshot(limit=max(1, min(limit, 500)))


@router.get("/model-hub")
async def stratum_model_hub():
    return get_model_hub_snapshot()


@router.get("/oracle")
async def stratum_oracle(limit: int = 10):
    return get_oracle_snapshot(limit=max(1, min(limit, 50)))


@router.get("/csie")
async def stratum_csie(limit: int = 10):
    return get_csie_snapshot(limit=max(1, min(limit, 50)))


@router.get("/causal-functor/diagnostics")
async def stratum_causal_functor_diagnostics(limit: int = 10):
    return get_causal_functor_diagnostics(limit=max(1, min(limit, 50)))
