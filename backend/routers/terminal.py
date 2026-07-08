"""
JULIUS Terminal Router — Exposes the Linux shell as API endpoints.
Provides terminal access through the frontend and chatbot.
"""

import logging
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..services.linux_shell import (
    execute_linux, execute_script, get_shell_status,
    get_linux_system_info, get_command_history, install_linux_package,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/terminal", tags=["Linux Terminal"])


class CommandRequest(BaseModel):
    command: str
    session_id: str = "default"
    timeout: int = 30


class ScriptRequest(BaseModel):
    script: str
    session_id: str = "default"
    timeout: int = 60


class InstallRequest(BaseModel):
    packages: str


@router.get("/status")
async def terminal_status():
    """Get Linux terminal subsystem status."""
    return get_shell_status()


@router.post("/execute")
async def run_command(req: CommandRequest):
    """Execute a Linux command."""
    result = execute_linux(req.command, req.session_id, req.timeout)
    return result


@router.post("/script")
async def run_script(req: ScriptRequest):
    """Execute a multi-line bash script."""
    result = execute_script(req.script, req.session_id, req.timeout)
    return result


@router.get("/sysinfo")
async def system_info():
    """Get Linux system information."""
    return get_linux_system_info()


@router.get("/history")
async def command_history(session_id: str = "default", limit: int = 20):
    """Get command history for a session."""
    return get_command_history(session_id, limit)


@router.post("/install")
async def install_packages(req: InstallRequest):
    """Install Linux packages via apt/yum/dnf/pacman."""
    return install_linux_package(req.packages)
