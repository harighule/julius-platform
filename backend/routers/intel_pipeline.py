from fastapi import APIRouter

router = APIRouter(prefix="/api/intel-pipeline", tags=["Intel Pipeline"])

@router.get("/status")
async def status():
    return {"status": "intel_pipeline module not yet implemented"}
