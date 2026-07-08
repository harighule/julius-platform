from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from ..security.auth import secure_endpoint
from ..services.bgp_mitm.node_control import (
    discover_nodes, control_node, execute_on_node, attack_node, get_controlled
)

router = APIRouter(prefix="/api/bgp-mitm/nodes", tags=["Node Control"])

class ControlRequest(BaseModel):
    node_id: str
    host: str
    port: int = 22
    username: str = "root"
    password: Optional[str] = None

class ExecuteRequest(BaseModel):
    node_id: str
    command: str

class AttackRequest(BaseModel):
    node_id: str
    attack_type: str = "mitm"

@router.post("/discover")
@secure_endpoint
async def api_discover_nodes(request: Request, max_nodes: int = 50):
    return {"nodes": discover_nodes(max_nodes), "total": max_nodes}

@router.post("/control")
@secure_endpoint
async def api_control_node(request: Request, req: ControlRequest):
    return control_node(req.node_id, req.host, req.port, req.username, req.password)

@router.post("/execute")
@secure_endpoint
async def api_execute_command(request: Request, req: ExecuteRequest):
    return execute_on_node(req.node_id, req.command)

@router.post("/attack")
@secure_endpoint
async def api_attack_node(request: Request, req: AttackRequest):
    return attack_node(req.node_id, req.attack_type)

@router.get("/controlled")
@secure_endpoint
async def api_get_controlled(request: Request):
    return {"controlled_nodes": get_controlled(), "total": len(get_controlled())}
