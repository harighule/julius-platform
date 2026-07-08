from fastapi import APIRouter

router = APIRouter(prefix="/api/csie", tags=["CSIE"])

@router.get("/status")
async def status():
    return {"status": "csie module not yet implemented"}
