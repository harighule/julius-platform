#!/usr/bin/env python3
"""
utils.py - Shared utilities for BGP MITM educational framework
Cross-platform: Windows, Linux, macOS
"""

import os
import sys
import subprocess
import platform
import logging
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
LOG_DIR = BASE_DIR / "data" / "bgp_mitm_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def setup_logging(name="bgp_mitm"):
    log_file = LOG_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(name)

def get_platform():
    return platform.system()

def enable_ip_forwarding():
    system = get_platform()
    try:
        if system == "Windows":
            subprocess.run(
                ["netsh", "interface", "ipv4", "set", "interface", "0", "forwarding=enabled"],
                capture_output=True, shell=True
            )
        else:
            subprocess.run(["sudo", "sysctl", "-w", "net.ipv4.ip_forward=1"], capture_output=True)
        return True
    except Exception:
        return False

def log_transaction(data):
    with open(LOG_DIR / "transactions.log", "a") as f:
        f.write(f"[{datetime.now()}] {data}\n")

def log_modification(data):
    with open(LOG_DIR / "modifications.log", "a") as f:
        f.write(f"[{datetime.now()}] {data}\n")