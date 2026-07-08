"""
JULIUS LAN Router — Network target reconnaissance and actions.
"""

import logging
import os
from typing import Optional
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from ..database import db
from ..services.lan_recon import (
    full_lan_recon, get_netbios_info, enumerate_smb_shares,
    detect_os, enumerate_users, check_smb_security,
    get_running_services, browse_smb_share,
)
from ..services.remote_ops import create_remote_folder, execute_remote_command, execute_remote_command_stream
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lan", tags=["LAN Operations"])


class TargetRequest(BaseModel):
    target: str
    username: Optional[str] = None
    password: Optional[str] = None


class RemoteFolderRequest(BaseModel):
    target: str
    path: str
    username: Optional[str] = None
    password: Optional[str] = None


class RemoteCommandRequest(BaseModel):
    target: str
    command: str
    username: Optional[str] = None
    password: Optional[str] = None


class BrowseRequest(BaseModel):
    target: str
    share: str
    path: str = ""
    username: Optional[str] = None
    password: Optional[str] = None


@router.post("/recon")
async def run_recon(req: TargetRequest):
    """Full reconnaissance on a LAN target — NetBIOS, SMB shares, OS detection, users, security."""
    result = full_lan_recon(req.target, req.username, req.password)
    db.add_event(
        event_id=f"evt_lan_recon_{req.target.replace('.','_')}",
        event_type="lan_recon",
        source="julius-lan-ops",
        data={"target": req.target, "shares": len(result.get("smb_shares", {}).get("shares", []))}
    )
    return result


@router.post("/netbios")
async def netbios_info(req: TargetRequest):
    return get_netbios_info(req.target)


@router.post("/shares")
async def list_shares(req: TargetRequest):
    return enumerate_smb_shares(req.target, req.username, req.password)


@router.post("/os")
async def os_detect(req: TargetRequest):
    return detect_os(req.target)


@router.post("/users")
async def list_users(req: TargetRequest):
    return enumerate_users(req.target, req.username, req.password)


@router.post("/security")
async def security_check(req: TargetRequest):
    return check_smb_security(req.target)


@router.post("/services")
async def running_services(req: TargetRequest):
    return get_running_services(req.target, req.username, req.password)


@router.post("/browse")
async def browse_share(req: BrowseRequest):
    return browse_smb_share(req.target, req.share, req.path, req.username, req.password)


@router.post("/mkdir")
async def make_folder(req: RemoteFolderRequest):
    return create_remote_folder(req.target, req.path, req.username, req.password)


@router.post("/exec")
async def run_command(req: RemoteCommandRequest):
    return execute_remote_command(req.target, req.command, req.username, req.password)


@router.post("/exec-stream")
async def run_command_stream(req: RemoteCommandRequest):
    return StreamingResponse(
        execute_remote_command_stream(req.target, req.command, req.username, req.password),
        media_type="text/plain"
    )


class StoreCredsRequest(BaseModel):
    target: str  # IP or "*" for default
    username: str
    password: str


@router.post("/credentials")
async def save_credentials(req: StoreCredsRequest):
    """Store credentials for a remote target."""
    from ..services.remote_ops import store_credentials
    store_credentials(req.target, req.username, req.password)
    return {"success": True, "target": req.target, "username": req.username}


@router.get("/credentials")
async def list_credentials():
    """List stored credential targets (passwords are masked)."""
    import json as _json
    from ..services.remote_ops import _CREDS_FILE
    try:
        if os.path.exists(_CREDS_FILE):
            with open(_CREDS_FILE, "r") as f:
                creds = _json.load(f)
            return {"targets": {k: {"username": v.get("username"), "has_password": bool(v.get("password"))} for k, v in creds.items()}}
    except Exception:
        pass
    return {"targets": {}}


@router.post("/test")
async def test_connection(req: TargetRequest):
    """Quick connectivity test to a LAN target."""
    import socket, subprocess
    results = {"target": req.target, "reachable": False, "ports": {}}

    # Ping
    try:
        ping = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", req.target],
            capture_output=True, text=True, timeout=5
        )
        results["reachable"] = ping.returncode == 0
    except Exception:
        pass

    # Test key ports
    for port, name in [(445, "SMB"), (5985, "WinRM"), (22, "SSH"), (3389, "RDP")]:
        try:
            sock = socket.create_connection((req.target, port), timeout=3)
            sock.close()
            results["ports"][name] = True
        except Exception:
            results["ports"][name] = False

    return results
