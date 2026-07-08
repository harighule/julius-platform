#!/usr/bin/env python3
"""
bgp_simulator.py - Real BGP hijack simulation using ExaBGP
"""

import os
import subprocess
import time
import tempfile
from datetime import datetime
from .utils import setup_logging, log_modification

logger = setup_logging("bgp_simulator")

EXABGP_CONFIG_TEMPLATE = """
neighbor 127.0.0.1 {
    router-id 10.0.0.1;
    local-as 65001;
    peer-as 65000;
    static {
        route 192.168.99.0/24 next-hop 10.0.0.1;
    }
}
"""

def run_bgp_simulation():
    # Write a dummy cut entry to modifications log
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dummy_entry = f"[{timestamp}] BGP simulation triggered (simulated cut)"
    log_modification(dummy_entry)
    logger.info("BGP simulation log entry added")

    try:
        subprocess.run(["which", "exabgp"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return {"status": "error", "engine": "exabgp", "message": "ExaBGP not installed. Install with: apt install exabgp"}

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.conf', delete=False) as f:
            f.write(EXABGP_CONFIG_TEMPLATE)
            config_path = f.name

        proc = subprocess.Popen(
            ["exabgp", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )
        with open("/tmp/exabgp_sim.pid", "w") as pf:
            pf.write(str(proc.pid))
        time.sleep(1)
        return {
            "status": "success",
            "engine": "exabgp",
            "message": f"ExaBGP started with PID {proc.pid}. Route announced.",
            "config": config_path,
            "pid": proc.pid,
            "log_entry": dummy_entry
        }
    except Exception as e:
        logger.error(f"ExaBGP simulation failed: {e}")
        return {"status": "error", "engine": "exabgp", "message": str(e)}

def stop_bgp_simulation():
    pid_file = "/tmp/exabgp_sim.pid"
    if os.path.exists(pid_file):
        with open(pid_file, "r") as pf:
            pid = int(pf.read().strip())
        try:
            os.killpg(os.getpgid(pid), 15)
            os.remove(pid_file)
            return {"status": "stopped", "pid": pid}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    return {"status": "not_running"}

def show_seed_lab_instructions():
    print("=" * 60)
    print("SEED BGP Lab - Educational BGP Hijacking Simulation")
    print("=" * 60)
    print("1. Download from: https://seedsecuritylabs.org/Labs_20.04/Networking/BGP/")
    print("2. The lab simulates a small Internet with multiple ASes")
    print("3. You can perform BGP prefix hijacking in a safe environment")
    print("4. Uses Docker containers to simulate routers")
    print("=" * 60)
