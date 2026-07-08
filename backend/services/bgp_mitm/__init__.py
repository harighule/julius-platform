"""
BGP MITM Educational Module - Julius Project
For educational purposes only.
"""

__version__ = "1.0.0"

from .utils import (
    setup_logging,
    log_transaction,
    log_modification,
    enable_ip_forwarding,
    get_platform
)
from .network_scanner import scan_network, get_gateway
from .arp_spoof import arp_spoof
from .packet_sniffer import start_sniffer
from .transaction_modifier import start_modifier
from .dns_spoof import start_dns_spoof
from .bgp_simulator import run_bgp_simulation
from .full_attack import run_attack
from .bgp_hijack_high import run_high_hijack, stop_high_hijack

__all__ = [
    "setup_logging",
    "log_transaction",
    "log_modification",
    "enable_ip_forwarding",
    "get_platform",
    "scan_network",
    "get_gateway",
    "arp_spoof",
    "start_sniffer",
    "start_modifier",
    "start_dns_spoof",
    "run_bgp_simulation",
    "run_attack",
    "run_high_hijack",
    "stop_high_hijack",
]