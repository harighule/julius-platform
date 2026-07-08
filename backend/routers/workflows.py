"""
JULIUS Workflow Router — Create, execute, and monitor multi-step investigation workflows.
"""

import asyncio
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..database import db
from ..services.workflow_engine import (
    execute_workflow, create_from_template, WORKFLOW_TEMPLATES
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflows", tags=["Workflows"])


class WorkflowCreate(BaseModel):
    name: str = ""
    description: str = ""
    steps: Optional[List[dict]] = None
    template: Optional[str] = None
    input_params: Optional[dict] = None


@router.get("/")
async def list_workflows():
    workflows = db.get_workflows()
    return {"workflows": workflows, "total": len(workflows)}


@router.post("/")
async def create_workflow(req: WorkflowCreate):
    if req.template:
        workflow_id = create_from_template(req.template, req.input_params or {})
        if not workflow_id:
            raise HTTPException(404, f"Template '{req.template}' not found")
        return {"workflow_id": workflow_id, "template": req.template, "status": "created"}

    if not req.name.strip():
        raise HTTPException(400, "name is required when not using a template")

    result = db.add_workflow(
        name=req.name,
        description=req.description,
        trigger_type="manual",
        actions=req.steps or [],
    )
    workflow_id = result["id"]

    if req.steps:
        for i, step in enumerate(req.steps):
            db.add_workflow_step(
                workflow_id, i,
                step.get("service", "unknown"),
                step.get("action", "unknown"),
                step.get("params", {}),
            )

    return {"workflow_id": workflow_id, "status": "created"}


@router.post("/{workflow_id}/execute")
async def run_workflow(workflow_id: int, background_tasks: BackgroundTasks):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")

    # FIX: Don't use asyncio.run() inside background_tasks — it creates a new event loop
    # which conflicts with FastAPI's existing loop. Use add_task directly with the coroutine.
    background_tasks.add_task(execute_workflow, workflow_id)
    return {"workflow_id": workflow_id, "status": "started"}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: int):
    wf = db.get_workflow_with_steps(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return wf


@router.get("/{workflow_id}/status")
async def get_workflow_status(workflow_id: int):
    wf = db.get_workflow(workflow_id)
    if not wf:
        raise HTTPException(404, "Workflow not found")
    steps = db.get_workflow_steps(workflow_id)
    completed = sum(1 for s in steps if s["status"] == "completed")
    failed = sum(1 for s in steps if s["status"] == "failed")
    return {
        "workflow_id": workflow_id,
        "name": wf["name"],
        "status": wf.get("status", "unknown"),
        "total_steps": len(steps),
        "completed_steps": completed,
        "failed_steps": failed,
        "progress_pct": round(completed / max(len(steps), 1) * 100),
    }


@router.post("/{workflow_id}/report")
async def generate_report(workflow_id: int, fmt: str = "json"):
    from ..services.report_generator import generate_report as gen_report
    filepath = gen_report(db, workflow_id, fmt)
    if not filepath:
        raise HTTPException(404, "Workflow not found")
    return {"workflow_id": workflow_id, "report_path": filepath, "format": fmt}


@router.get("/templates/list")
async def list_templates():
    return {
        "templates": {
            name: {"name": t["name"], "description": t["description"], "steps": len(t["steps"])}
            for name, t in WORKFLOW_TEMPLATES.items()
        }
    }


# ── Auto-start workflows on system boot ──────────────────────────────────

async def run_autonomous_workflows():
    """
    Runs automatically on startup.
    Creates and executes the recon workflow on localhost
    so the system starts collecting data immediately without
    any manual input from the user.
    """
    try:
        logger.info("Starting autonomous workflow: recon on localhost")
        workflow_id = create_from_template("recon", {"target": "127.0.0.1"})
        if workflow_id:
            await execute_workflow(workflow_id)
            logger.info(f"Autonomous recon workflow {workflow_id} completed")
        else:
            logger.warning("Failed to create autonomous recon workflow")
    except Exception as e:
        logger.error(f"Autonomous workflow error: {e}")