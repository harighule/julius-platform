"""
JULIUS Network Router — Authorized network monitoring with rate limiting.
Allowlist is persisted in the database.
"""

import logging
import socket
import time
import ipaddress
from typing import Optional, List, Dict, Tuple
from datetime import datetime
from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/network", tags=["Network Monitoring"])


BLOCKED_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
]

DEFAULT_RANGES = [
    ("192.168.0.0/16", "Private Class C", "system", "Default local network"),
    ("10.0.0.0/8", "Private Class A", "system", "Default private range"),
    ("172.16.0.0/12", "Private Class B", "system", "Default private range"),
    ("127.0.0.0/8", "Loopback", "system", "Localhost"),
]


def _seed_default_allowlist():
    existing = db.get_active_allowlist()
    existing_cidrs = {e["cidr_range"] for e in existing}
    for cidr, label, added_by, notes in DEFAULT_RANGES:
        if cidr not in existing_cidrs:
            db.add_allowlist_entry(cidr, label, added_by, notes)


_rate_state: Dict[str, List[float]] = {}
RATE_LIMIT_MAX = 20
RATE_LIMIT_WINDOW = 60


def _check_rate_limit(user_id: str) -> Tuple[bool, int, int]:
    now = time.time()
    if user_id not in _rate_state:
        _rate_state[user_id] = []
    _rate_state[user_id] = [t for t in _rate_state[user_id] if now - t < RATE_LIMIT_WINDOW]
    used = len(_rate_state[user_id])
    remaining = max(0, RATE_LIMIT_MAX - used)
    if used >= RATE_LIMIT_MAX:
        return False, used, remaining
    _rate_state[user_id].append(now)
    return True, used + 1, remaining - 1


def _is_authorized(ip_str: str) -> Tuple[bool, str]:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, "Invalid IP address"

    for blocked in BLOCKED_NETWORKS:
        if addr in blocked:
            return False, f"Blocked: {blocked}"

    allowlist = db.get_active_allowlist()
    for entry in allowlist:
        try:
            net = ipaddress.ip_network(entry["cidr_range"], strict=False)
            if addr in net:
                return True, f"Authorized via {entry['label']} ({entry['cidr_range']})"
        except ValueError:
            continue

    if not addr.is_private:
        return True, "Public IP allowed"

    return False, "IP not in authorized ranges"


class PortCheckRequest(BaseModel):
    ip: str
    port: int
    timeout: float = 3.0

class AddRangeRequest(BaseModel):
    cidr: str
    label: str
    added_by: str = "admin"
    notes: str = ""

class RemoveRangeRequest(BaseModel):
    cidr: str


@router.post("/check-port")
async def check_port(body: PortCheckRequest, request: Request):
    user_id = request.headers.get("X-User-ID", "anonymous")

    authorized, reason = _is_authorized(body.ip)
    if not authorized:
        return {"status": "blocked", "ip": body.ip, "port": body.port, "message": reason}

    allowed, used, remaining = _check_rate_limit(user_id)
    if not allowed:
        return {"status": "rate_limited", "ip": body.ip, "port": body.port,
                "message": "Rate limit exceeded", "checks_used": used}

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(min(body.timeout, 5.0))
            result = s.connect_ex((body.ip, body.port))
            status = "open" if result == 0 else "closed"
    except socket.timeout:
        status = "filtered"
    except Exception:
        status = "error"

    return {
        "status": status,
        "ip": body.ip,
        "port": body.port,
        "authorized_via": reason,
        "checks_remaining": remaining,
    }


@router.get("/rate-limit-status")
async def rate_limit_status(request: Request):
    user_id = request.headers.get("X-User-ID", "anonymous")
    now = time.time()
    checks = _rate_state.get(user_id, [])
    checks = [t for t in checks if now - t < RATE_LIMIT_WINDOW]
    return {
        "checks_used": len(checks),
        "checks_remaining": max(0, RATE_LIMIT_MAX - len(checks)),
        "window_seconds": RATE_LIMIT_WINDOW,
    }


@router.get("/info")
async def monitor_info():
    allowlist = db.get_active_allowlist()
    return {
        "service": "JULIUS Network Monitor",
        "version": "1.0.0",
        "capabilities": ["tcp_connectivity_check"],
        "authorization": {
            "mode": "cidr_allowlist",
            "allow_public_by_default": True,
            "authorized_ranges": [
                {"cidr": e["cidr_range"], "label": e["label"], "added_by": e["added_by"]}
                for e in allowlist
            ],
            "total_ranges": len(allowlist),
        },
        "constraints": {
            "rate_limits": {
                "per_user": f"{RATE_LIMIT_MAX} checks / {RATE_LIMIT_WINDOW}s",
            },
            "security": [
                "No payload transmission",
                "Immediate socket close",
                "CIDR authorization",
                "Full audit logging",
            ],
        },
    }


@router.get("/allowlist")
async def list_allowlist():
    allowlist = db.get_active_allowlist()
    return {
        "authorized_ranges": [
            {"cidr": e["cidr_range"], "label": e["label"], "added_by": e["added_by"], "added_at": e["created_at"]}
            for e in allowlist
        ],
    }


@router.post("/allowlist/add")
async def add_range(body: AddRangeRequest):
    try:
        ipaddress.ip_network(body.cidr, strict=False)
    except ValueError as e:
        return {"success": False, "message": str(e)}
    result = db.add_allowlist_entry(body.cidr, body.label, body.added_by, body.notes)
    return {"success": True, "message": f"Added {body.cidr}", "result": result}


@router.post("/allowlist/remove")
async def remove_range(body: RemoveRangeRequest):
    db.remove_allowlist_entry(body.cidr)
    return {"success": True, "message": f"Removed {body.cidr}"}


@router.get("/allowlist/check/{ip}")
async def check_authorization(ip: str):
    authorized, reason = _is_authorized(ip)
    return {"ip": ip, "authorized": authorized, "reason": reason}


# Seed defaults on import
try:
    _seed_default_allowlist()
except Exception:
    pass
