#!/usr/bin/env python3
"""
packet_sniffer.py - Packet sniffer with crypto address detection
"""

from scapy.all import sniff, IP, TCP
import re
from .utils import setup_logging, log_transaction

logger = setup_logging("packet_sniffer")

PATTERNS = {
    "Bitcoin": r"1[1-9A-HJ-NP-Za-km-z]{25,34}|3[1-9A-HJ-NP-Za-km-z]{25,34}|bc1[a-z0-9]{39,59}",
    "Ethereum": r"0x[a-fA-F0-9]{40}",
    "Monero": r"4[1-9A-HJ-NP-Za-km-z]{94}",
    "Litecoin": r"[LM][1-9A-HJ-NP-Za-km-z]{26,33}",
    "Dogecoin": r"D[1-9A-HJ-NP-Za-km-z]{33}",
}

def detect_crypto(packet):
    if packet.haslayer(TCP) and packet.haslayer(IP):
        try:
            payload = bytes(packet[TCP].payload).decode('utf-8', errors='ignore')
            for name, pattern in PATTERNS.items():
                matches = re.findall(pattern, payload)
                for match in matches:
                    msg = f"[{name}] {match} | {packet[IP].src} -> {packet[IP].dst}"
                    print(f"[+] {msg}")
                    log_transaction(msg)
        except:
            pass

def start_sniffer(interface=None, timeout=None):
    if not interface:
        interface = "eth0"
    logger.info(f"Starting packet sniffer on {interface}")
    sniff(iface=interface, prn=detect_crypto, store=0, timeout=timeout)