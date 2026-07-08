"""
JULIUS LAN Reconnaissance — Deep enumeration of Windows targets on the local network.
Exploits open SMB (445), NetBIOS (139), MSRPC (135) ports for intelligence gathering.
"""

import subprocess
import socket
import re
import logging
import os
from typing import Dict, Any, List
from .utils import safe_strip

logger = logging.getLogger(__name__)


def full_lan_recon(target: str, username: str = None, password: str = None) -> Dict[str, Any]:
    """Run all available reconnaissance on a LAN target."""
    results = {
        "target": target,
        "netbios_info": get_netbios_info(target),
        "smb_shares": enumerate_smb_shares(target, username, password),
        "os_info": detect_os(target),
        "users": enumerate_users(target, username, password),
        "smb_security": check_smb_security(target),
        "services": get_running_services(target, username, password),
        "network_info": get_network_config(target, username, password),
    }
    return results


def get_netbios_info(target: str) -> Dict:
    """Get NetBIOS name, domain, MAC via nbtstat."""
    result = {"hostname": None, "domain": None, "mac": None, "services": []}
    try:
        out = subprocess.run(
            ["nbtstat", "-A", target], capture_output=True, text=True, timeout=10
        )
        lines = out.stdout.split("\n")
        for line in lines:
            line = safe_strip(line)
            if "<00>" in line and "UNIQUE" in line:
                name = safe_strip(line.split("<00>")[0])
                if not result["hostname"]:
                    result["hostname"] = name
            if "<00>" in line and "GROUP" in line:
                result["domain"] = safe_strip(line.split("<00>")[0])
            if "<20>" in line:
                result["services"].append(safe_strip(line.split("<20>")[0]))

        mac_match = re.search(r'MAC Address = ([0-9A-Fa-f-]{17})', out.stdout)
        if mac_match:
            result["mac"] = mac_match.group(1)
    except Exception as e:
        result["error"] = str(e)
    return result


def enumerate_smb_shares(target: str, username: str = None, password: str = None) -> Dict:
    """List SMB shared folders on the target."""
    result = {"shares": [], "accessible": False}
    try:
        # Disconnect stale
        subprocess.run(["net", "use", f"\\\\{target}\\IPC$", "/delete", "/y"],
                       capture_output=True, text=True, timeout=5)

        # Connect
        cmd = ["net", "use", f"\\\\{target}\\IPC$"]
        if username and password:
            cmd += [f"/user:{username}", password]
        else:
            cmd += ["/user:", ""]  # null session attempt

        auth = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # List shares
        view = subprocess.run(
            ["net", "view", f"\\\\{target}"], capture_output=True, text=True, timeout=10
        )

        if view.returncode == 0:
            result["accessible"] = True
            for line in view.stdout.split("\n"):
                line = safe_strip(line)
                if line and not line.startswith("-") and not line.startswith("Shared") and not line.startswith("The command"):
                    parts = re.split(r'\s{2,}', line)
                    if parts and parts[0]:
                        share = {"name": parts[0]}
                        if len(parts) > 1:
                            share["type"] = parts[1]
                        if len(parts) > 2:
                            share["remark"] = parts[2]
                        result["shares"].append(share)
        else:
            result["error"] = safe_strip(view.stderr)[:200]

        # Cleanup
        subprocess.run(["net", "use", f"\\\\{target}\\IPC$", "/delete", "/y"],
                       capture_output=True, text=True, timeout=5)
    except Exception as e:
        result["error"] = str(e)
    return result


def detect_os(target: str) -> Dict:
    """Detect OS version from SMB/NetBIOS responses and TTL."""
    result = {"os": None, "ttl": None, "arch": None}
    try:
        ping = subprocess.run(
            ["ping", "-n", "1", "-w", "2000", target],
            capture_output=True, text=True, timeout=5
        )
        ttl_match = re.search(r'TTL=(\d+)', ping.stdout, re.IGNORECASE)
        if ttl_match:
            ttl = int(ttl_match.group(1))
            result["ttl"] = ttl
            if ttl <= 64:
                result["os"] = "Linux/macOS (TTL ~64)"
            elif ttl <= 128:
                result["os"] = "Windows (TTL ~128)"
            else:
                result["os"] = f"Unknown (TTL {ttl})"
    except Exception as e:
        result["error"] = str(e)
    return result


def enumerate_users(target: str, username: str = None, password: str = None) -> Dict:
    """Enumerate user accounts via WMI or net commands."""
    result = {"users": [], "method": None}
    try:
        cmd = ["wmic", f"/node:{target}"]
        if username and password:
            cmd += [f"/user:{username}", f"/password:{password}"]
        cmd += ["useraccount", "get", "Name,Status,Disabled,Lockout"]

        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and "Name" in out.stdout:
            result["method"] = "WMI"
            for line in safe_strip(out.stdout).split("\n")[1:]:
                parts = safe_strip(line).split()
                if parts:
                    user = {"name": parts[0]}
                    if len(parts) > 1:
                        user["disabled"] = parts[1] if len(parts) > 1 else "?"
                    result["users"].append(user)
        else:
            result["error"] = safe_strip(out.stderr)[:200] or "WMI access denied"
    except Exception as e:
        result["error"] = str(e)
    return result


def check_smb_security(target: str) -> Dict:
    """Check SMB security configuration — signing, version, null sessions."""
    result = {"smb_signing": "unknown", "null_session": False, "vulnerabilities": []}
    try:
        # Null session test
        null = subprocess.run(
            ["net", "use", f"\\\\{target}\\IPC$", "/user:", ""],
            capture_output=True, text=True, timeout=10
        )
        if null.returncode == 0:
            result["null_session"] = True
            result["vulnerabilities"].append("SMB null session allowed — information disclosure risk")
        subprocess.run(["net", "use", f"\\\\{target}\\IPC$", "/delete", "/y"],
                       capture_output=True, text=True, timeout=5)

        # Check if common admin shares are accessible
        for share in ["C$", "ADMIN$"]:
            try:
                test = subprocess.run(
                    ["cmd", "/c", f"dir \\\\{target}\\{share}"],
                    capture_output=True, text=True, timeout=5
                )
                if test.returncode == 0:
                    result["vulnerabilities"].append(f"Admin share \\\\{target}\\{share} is accessible")
            except Exception:
                pass

    except Exception as e:
        result["error"] = str(e)
    return result


def get_running_services(target: str, username: str = None, password: str = None) -> Dict:
    """Get running services via WMI."""
    result = {"services": [], "total": 0}
    try:
        cmd = ["wmic", f"/node:{target}"]
        if username and password:
            cmd += [f"/user:{username}", f"/password:{password}"]
        cmd += ["service", "where", "State='Running'", "get", "Name,DisplayName,StartMode"]

        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and "Name" in out.stdout:
            for line in safe_strip(out.stdout).split("\n")[1:]:
                parts = re.split(r'\s{2,}', safe_strip(line))
                if parts and parts[0]:
                    svc = {"display_name": parts[0]}
                    if len(parts) > 1:
                        svc["name"] = parts[1]
                    result["services"].append(svc)
            result["total"] = len(result["services"])
        else:
            result["error"] = safe_strip(out.stderr)[:200] or "WMI access denied"
    except Exception as e:
        result["error"] = str(e)
    return result


def get_network_config(target: str, username: str = None, password: str = None) -> Dict:
    """Get network configuration via WMI."""
    result = {"adapters": []}
    try:
        cmd = ["wmic", f"/node:{target}"]
        if username and password:
            cmd += [f"/user:{username}", f"/password:{password}"]
        cmd += ["nicconfig", "where", "IPEnabled=TRUE", "get",
                "Description,IPAddress,MACAddress,DefaultIPGateway,DHCPEnabled"]

        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and "Description" in out.stdout:
            for line in safe_strip(out.stdout).split("\n")[1:]:
                parts = re.split(r'\s{2,}', safe_strip(line))
                if parts and parts[0]:
                    result["adapters"].append({"description": parts[0], "raw": safe_strip(line)[:200]})
        else:
            result["error"] = safe_strip(out.stderr)[:200] or "WMI access denied"
    except Exception as e:
        result["error"] = str(e)
    return result


def browse_smb_share(target: str, share: str, path: str = "", username: str = None, password: str = None) -> Dict:
    """Browse files on an SMB share."""
    result = {"files": [], "path": f"\\\\{target}\\{share}\\{path}"}
    try:
        if username and password:
            subprocess.run(["net", "use", f"\\\\{target}\\{share}", f"/user:{username}", password],
                           capture_output=True, text=True, timeout=10)

        full = f"\\\\{target}\\{share}\\{path}" if path else f"\\\\{target}\\{share}"
        out = subprocess.run(["cmd", "/c", f"dir \"{full}\""],
                             capture_output=True, text=True, timeout=10)

        if out.returncode == 0:
            for line in out.stdout.split("\n"):
                line = safe_strip(line)
                if line and not line.startswith("Volume") and not line.startswith("Directory") and "File(s)" not in line and "Dir(s)" not in line and "bytes" not in line.lower():
                    match = re.match(r'(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2}\s+[AP]M)\s+(<DIR>|\S+)\s+(.*)', line)
                    if match:
                        result["files"].append({
                            "date": match.group(1),
                            "time": match.group(2),
                            "type": "dir" if match.group(3) == "<DIR>" else "file",
                            "size": match.group(3) if match.group(3) != "<DIR>" else None,
                            "name": safe_strip(match.group(4)),
                        })
        else:
            result["error"] = safe_strip(out.stderr)[:200]
    except Exception as e:
        result["error"] = str(e)
    return result
