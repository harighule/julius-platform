"""
JULIUS full intelligence report export routes.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.intelligence_report import generate_full_report_bundle, get_generated_report_file

router = APIRouter(prefix="/api/reports", tags=["Reports"])


@router.post("/full/generate")
async def generate_full_report():
    try:
        return await generate_full_report_bundle()
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        print(f"REPORT GENERATION ERROR:\n{error_detail}")
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {str(e)}"
        )


@router.get("/full/{report_id}/{fmt}")
async def download_full_report(report_id: str, fmt: str):
    try:
        path, media_type = get_generated_report_file(report_id, fmt)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported report format") from exc

    return FileResponse(
        path=str(path),
        media_type=media_type,
        filename=path.name,
    )
