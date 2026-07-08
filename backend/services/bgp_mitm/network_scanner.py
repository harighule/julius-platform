#!/usr/bin/env python3
"""
network_scanner.py - Cross-platform host discovery
WITHOUT netifaces dependency
"""

import subprocess
import platform
import ipaddress
import concurrent.futures
import socket
import os
import re
from .utils import setup_logging

logger = setup_logging("network_scanner")


def get_local_ip():
    """Get local IP address using socket (no external dependencies)"""
    try:
        # Connect to a public DNS server to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def get_network_interfaces():
    """Get network interfaces without netifaces"""
    interfaces = []
    system = platform.system()
    
    try:
        if system == "Windows":
            # Use ipconfig on Windows
            output = subprocess.check_output("ipconfig", shell=True, text=True)
            lines = output.splitlines()
            current_iface = None
            
            for line in lines:
                # Detect adapter name
                if "adapter" in line.lower():
                    current_iface = line.strip().replace("adapter", "").replace(":", "").strip()
                # Detect IPv4 address
                elif "IPv4" in line and current_iface:
                    parts = line.split(":")
                    if len(parts) > 1:
                        ip = parts[1].strip()
                        # Filter out loopback
                        if not ip.startswith("127."):
                            interfaces.append({
                                "name": current_iface,
                                "ip": ip
                            })
        
        elif system == "Linux":
            # Use ip addr on Linux
            output = subprocess.check_output(["ip", "addr"], text=True)
            for line in output.splitlines():
                if "inet " in line and "127.0.0.1" not in line:
                    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        interfaces.append({
                            "name": "Linux_interface",
                            "ip": match.group(1)
                        })
        
        elif system == "Darwin":  # macOS
            output = subprocess.check_output(["ifconfig"], text=True)
            for line in output.splitlines():
                if "inet " in line and "127.0.0.1" not in line:
                    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", line)
                    if match:
                        interfaces.append({
                            "name": "macOS_interface",
                            "ip": match.group(1)
                        })
    
    except Exception as e:
        logger.warning(f"Could not detect network interfaces: {e}")
        # Fallback to simple local IP
        ip = get_local_ip()
        interfaces.append({"name": "default", "ip": ip})
    
    return interfaces


def ping_host(ip, timeout=2):
    """Ping a host to check if it's alive"""
    system = platform.system()
    try:
        if system == "Windows":
            cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), str(ip)]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout), str(ip)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+1)
        return result.returncode == 0
    except:
        return False


def scan_network(ip_range="192.168.1.0/24", max_workers=50):
    """Scan network for active hosts"""
    try:
        network = ipaddress.ip_network(ip_range, strict=False)
    except ValueError:
        # If invalid range, try to detect from local IP
        local_ip = get_local_ip()
        if local_ip != "127.0.0.1":
            # Use /24 subnet based on local IP
            base_ip = ".".join(local_ip.split(".")[:3])
            ip_range = f"{base_ip}.0/24"
            network = ipaddress.ip_network(ip_range, strict=False)
        else:
            logger.error("Could not determine network range")
            return []
    
    hosts = []
    logger.info(f"Scanning {ip_range} with {max_workers} threads...")
    
    def check_host(ip):
        if ping_host(str(ip)):
            return str(ip)
        return None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(check_host, network.hosts())
        hosts = [ip for ip in results if ip]
    
    logger.info(f"Found {len(hosts)} active hosts")
    return hosts


def get_gateway():
    """Get default gateway without netifaces"""
    system = platform.system()
    try:
        if system == "Windows":
            # Use route print on Windows
            result = subprocess.run(["route", "print", "0.0.0.0"], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if "0.0.0.0" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        # Find the gateway IP
                        for part in parts:
                            if re.match(r"^\d+\.\d+\.\d+\.\d+$", part):
                                return part
        else:
            # Use ip route on Linux/Mac
            result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
            match = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
            if match:
                return match.group(1)
    except Exception as e:
        logger.error(f"Error getting gateway: {e}")
    
    # Fallback: try to guess gateway from local IP
    local_ip = get_local_ip()
    if local_ip != "127.0.0.1":
        parts = local_ip.split(".")
        parts[3] = "1"
        return ".".join(parts)
    
    return "192.168.1.1"  # Common default