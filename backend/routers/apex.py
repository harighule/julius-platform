from fastapi import APIRouter

router = APIRouter(prefix="/api/apex", tags=["Apex"])

@router.get("/status")
async def status():
    return {"status": "apex module not yet implemented"}
