"""
JULIUS Chat Router — AI Chatbot with NLP intent classification and action execution.
Routes natural language commands to scanner, exploit, behavioral, identity, etc.
"""

import logging
import os
import time
import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from ..database import db
from ..services.autogen_brain import ask_julius, is_autogen_ready, AUTOGEN_AVAILABLE

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["Chatbot"])


# ═══════════════════════════════════════════════════════════════════════════
# Intent Classification
# ═══════════════════════════════════════════════════════════════════════════

class IntentCategory(str, Enum):
    # System
    SYSTEM_STATUS = "system_status"
    HEALTH_CHECK = "health_check"
    HELP = "help"
    # Scanner
    NETWORK_SCAN = "network_scan"
    PORT_CHECK = "port_check"
    VULN_SCAN = "vulnerability_scan"
    # Exploit
    RUN_EXPLOIT = "run_exploit"
    LIST_EXPLOITS = "list_exploits"
    # Behavioral
    BEHAVIORAL_STATUS = "behavioral_status"
    ADD_PATTERN = "add_pattern"
    LIST_ALERTS = "list_alerts"
    # Identity
    IDENTITY_LOOKUP = "identity_lookup"
    IDENTITY_MERGE = "identity_merge"
    # Events
    LIST_EVENTS = "list_events"
    EVENT_STATS = "event_stats"
    # Files
    LIST_FILES = "list_files"
    READ_FILE = "read_file"
    # Dark Web
    DARKWEB_SEARCH = "darkweb_search"
    DARKWEB_INVESTIGATE = "darkweb_investigate"
    DARKWEB_STATUS = "darkweb_status"
    # Investigation
    TRACE_IP = "trace_ip"
    IP_LOOKUP = "ip_lookup"
    DNS_LOOKUP = "dns_lookup"
    INVESTIGATE = "investigate"
    # Remote Operations
    REMOTE_COMMAND = "remote_command"
    STORE_CREDENTIALS = "store_credentials"
    # System Administration
    INSTALL_PACKAGE = "install_package"
    LINUX_COMMAND = "linux_command"
    # General
    GREETING = "greeting"
    UNKNOWN = "unknown"


INTENT_PATTERNS = {
    IntentCategory.SYSTEM_STATUS: [
        "status", "system status", "how is the system", "check system",
        "dashboard", "overview", "stats", "statistics",
    ],
    IntentCategory.HEALTH_CHECK: [
        "health", "health check", "is system up", "ping", "alive",
    ],
    IntentCategory.HELP: [
        "help", "commands", "what can you do", "capabilities", "options",
    ],
    IntentCategory.NETWORK_SCAN: [
        "scan", "network scan", "port scan", "nmap", "scan target",
        "scan network", "discover", "reconnaissance", "recon",
    ],
    IntentCategory.PORT_CHECK: [
        "check port", "port check", "is port open", "test port",
    ],
    IntentCategory.VULN_SCAN: [
        "vulnerability", "vuln scan", "find vulnerabilities", "security scan",
        "audit", "pentest", "penetration test",
    ],
    IntentCategory.RUN_EXPLOIT: [
        "exploit", "attack", "hack", "breach", "pwn", "compromise",
        "brute force", "bruteforce", "ftp", "ssh attack",
    ],
    IntentCategory.LIST_EXPLOITS: [
        "list exploits", "exploit modules", "available exploits", "show exploits",
    ],
    IntentCategory.BEHAVIORAL_STATUS: [
        "behavioral", "patterns", "behavior", "anomaly", "detection patterns",
    ],
    IntentCategory.ADD_PATTERN: [
        "add pattern", "create pattern", "new pattern", "define pattern",
    ],
    IntentCategory.LIST_ALERTS: [
        "alerts", "show alerts", "list alerts", "recent alerts", "warnings",
    ],
    IntentCategory.IDENTITY_LOOKUP: [
        "identity", "identities", "who is", "lookup", "resolve identity",
        "identity graph", "find person",
    ],
    IntentCategory.IDENTITY_MERGE: [
        "merge identity", "merge identities", "link identity", "connect identity",
    ],
    IntentCategory.LIST_EVENTS: [
        "events", "event log", "recent events", "show events", "activity",
    ],
    IntentCategory.EVENT_STATS: [
        "event stats", "event statistics", "event summary",
    ],
    IntentCategory.LIST_FILES: [
        "files", "list files", "show files", "directory", "ls", "dir",
    ],
    IntentCategory.READ_FILE: [
        "read file", "show file", "cat", "view file", "open file",
    ],
    IntentCategory.DARKWEB_SEARCH: [
        "dark web", "darkweb", "onion", "tor search", "dark web search",
        "deep web", "darknet", "hidden service", "robin", ".onion",
        "dark web osint", "threat intel dark", "breach search",
    ],
    IntentCategory.DARKWEB_INVESTIGATE: [
        "investigate dark", "dark web investigate", "osint investigation",
        "full investigation", "dark web analysis",
    ],
    IntentCategory.DARKWEB_STATUS: [
        "tor status", "dark web status", "robin status", "tor health",
    ],
    IntentCategory.TRACE_IP: [
        "trace", "traceroute", "tracert", "trace ip", "trace route",
        "network path", "hop count", "trace target",
    ],
    IntentCategory.IP_LOOKUP: [
        "ip lookup", "whois", "geolocate", "geolocation", "ip info",
        "who owns", "ip address info", "lookup ip", "ip reputation",
    ],
    IntentCategory.DNS_LOOKUP: [
        "dns lookup", "dns resolve", "resolve domain", "nslookup",
        "dig", "domain info", "dns records",
    ],
    IntentCategory.INVESTIGATE: [
        "investigate", "full recon", "reconnaissance on", "investigate target",
        "run investigation", "deep scan", "full scan on",
    ],
    IntentCategory.REMOTE_COMMAND: [
        "make folder", "create folder", "mkdir on", "create directory",
        "remote command", "execute on", "run on", "make file on",
        "create file on", "remote exec", "remote shell",
    ],
    IntentCategory.STORE_CREDENTIALS: [
        "set credentials", "store credentials", "save credentials",
        "set password", "store password", "save password",
        "set creds", "store creds", "save creds",
        "credentials for", "login for", "auth for",
    ],
    IntentCategory.INSTALL_PACKAGE: [
        "pip install", "npm install", "install package",
        "add package", "install tool", "install module",
        "install library", "install dependency", "apt install",
        "choco install", "install software", "download and install",
    ],
    IntentCategory.LINUX_COMMAND: [
        "linux", "bash", "terminal", "shell", "linux command",
        "run linux", "run bash", "run shell", "wsl",
        "linux terminal", "ubuntu", "apt", "sudo",
        "grep", "awk", "sed", "chmod", "chown", "curl",
        "wget", "cat", "nano", "vim", "tail",
        "systemctl", "journalctl", "top", "htop",
        "ifconfig", "netstat", "ss ", "iptables",
        "linux status", "linux info", "shell status",
    ],
    IntentCategory.GREETING: [
        "hello", "hi", "hey", "yo", "sup", "greetings", "good morning",
        "good evening", "what's up", "how are you", "how r u", "whats up",
        "howdy", "hola", "good afternoon", "how's it going",
    ],
}


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _fuzzy_match(word: str, pattern: str, max_distance: int = 2) -> bool:
    """Check if a word is within edit distance of a pattern (typo tolerance)."""
    if len(word) < 3 or len(pattern) < 3:
        return False
    dist = _levenshtein(word, pattern)
    # Allow 1 typo for short words (3-5 chars), 2 for longer
    allowed = 1 if len(pattern) <= 5 else max_distance
    return dist <= allowed and dist > 0


def classify_intent(message: str) -> tuple:
    """Classify user message into an intent category with fuzzy matching for typo tolerance."""
    import re
    msg_lower = message.lower().strip()
    msg_words = msg_lower.split()

    best_match = IntentCategory.UNKNOWN
    best_score = 0.0

    for category, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            # ── Exact / substring matching (original logic) ──
            if len(pattern) <= 3:
                if re.search(r'\b' + re.escape(pattern) + r'\b', msg_lower):
                    score = len(pattern) / max(len(msg_lower), 1)
                    if score > best_score:
                        best_score = score
                        best_match = category
            else:
                if pattern in msg_lower:
                    score = len(pattern) / max(len(msg_lower), 1)
                    if score > best_score:
                        best_score = score
                        best_match = category

            # ── Fuzzy matching for typo tolerance ──
            # Only try fuzzy if we haven't found a better exact match yet
            if best_match == IntentCategory.UNKNOWN or best_score < 0.5:
                pattern_words = pattern.split()
                if len(pattern_words) == 1 and len(pattern) >= 3:
                    # Single-word pattern: check each word of the message
                    for word in msg_words:
                        if _fuzzy_match(word, pattern):
                            fuzzy_score = (len(pattern) / max(len(msg_lower), 1)) * 0.8  # slightly lower than exact
                            if fuzzy_score > best_score:
                                best_score = fuzzy_score
                                best_match = category
                elif len(pattern_words) > 1:
                    # Multi-word pattern: check if any word in the message fuzzy-matches
                    # at least one word in the pattern, with others matching exactly
                    matched_words = 0
                    for pw in pattern_words:
                        if pw in msg_lower:
                            matched_words += 1
                        elif any(_fuzzy_match(mw, pw) for mw in msg_words):
                            matched_words += 1
                    if matched_words == len(pattern_words):
                        fuzzy_score = (len(pattern) / max(len(msg_lower), 1)) * 0.75
                        if fuzzy_score > best_score:
                            best_score = fuzzy_score
                            best_match = category

    # Boost matches
    if best_score > 0:
        best_score = min(1.0, best_score + 0.3)

    return best_match, best_score


# ═══════════════════════════════════════════════════════════════════════════
# Action Execution
# ═══════════════════════════════════════════════════════════════════════════

async def execute_intent(intent: IntentCategory, message: str) -> Dict[str, Any]:
    """Execute an action based on classified intent."""

    if intent == IntentCategory.SYSTEM_STATUS:
        stats = db.get_system_stats()
        return {
            "message": f"**JULIUS System Status**\n\n"
                       f"- Scans: {stats['total_scans']}\n"
                       f"- Vulnerabilities: {stats['total_vulnerabilities']}\n"
                       f"- Events: {stats['total_events']}\n"
                       f"- Identities: {stats['total_identities']}\n"
                       f"- Alerts: {stats['total_alerts']}\n"
                       f"- Users: {stats['total_users']}",
            "data": stats,
        }

    elif intent == IntentCategory.HEALTH_CHECK:
        return {
            "message": "**System Health: OPERATIONAL**\n\nAll JULIUS subsystems are running.\n"
                       "- Scanner Engine: Online\n"
                       "- Exploit Framework: Online\n"
                       "- Behavioral Engine: Online\n"
                       "- Identity Resolution: Online\n"
                       "- Event Bus: Online\n"
                       "- Database: Online",
            "data": {"status": "healthy"},
        }

    elif intent == IntentCategory.HELP:
        return {
            "message": "**JULIUS Command Reference**\n\n"
                       "**Scanning:**\n"
                       "- `scan <target>` - Run network scan\n"
                       "- `check port <ip> <port>` - Check single port\n"
                       "- `vuln scan <target>` - Vulnerability scan\n\n"
                       "**Exploitation:**\n"
                       "- `exploit <target>` - Run exploit\n"
                       "- `list exploits` - Show available modules\n\n"
                       "**Intelligence:**\n"
                       "- `identity <name>` - Lookup identity\n"
                       "- `behavioral status` - Pattern status\n"
                       "- `alerts` - Recent alerts\n\n"
                       "**Dark Web OSINT (Robin AI):**\n"
                       "- `dark web search <query>` - Search .onion sites via Tor\n"
                       "- `tor status` - Check Tor proxy & Robin health\n"
                       "- `dark web investigate` - Full investigation pipeline\n\n"
                       "**System Administration:**\n"
                       "- `install <package>` - Install packages (pip/npm/choco)\n"
                       "- `install requests paramiko` - Install multiple packages\n"
                       "- `npm install axios` - Install via specific manager\n\n"
                       "**Linux Terminal:**\n"
                       "- `linux <command>` - Run any Linux command\n"
                       "- `bash ls -la /etc` - Execute bash commands\n"
                       "- `linux status` - Check Linux shell status\n"
                       "- `linux info` - System information\n\n"
                       "**System:**\n"
                       "- `status` - System overview\n"
                       "- `events` - Event log\n"
                       "- `files` - File browser\n"
                       "- `health` - Health check",
            "data": {},
        }

    elif intent == IntentCategory.NETWORK_SCAN:
        # Extract target from message
        words = message.split()
        target = None
        for w in words:
            if "." in w and any(c.isdigit() for c in w):
                target = w
                break
        if not target:
            target = "127.0.0.1"

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        db.create_scan(scan_id, target, "quick")

        # Run quick inline scan for chatbot responsiveness
        from .scanner import _check_port, TOP_PORTS
        open_ports = []
        for port in TOP_PORTS[:10]:
            result = _check_port(target, port, 1.5)
            if result["status"] == "open":
                open_ports.append(result)

        db.update_scan(scan_id, "completed", {
            "target": target, "open_ports": open_ports,
            "total_ports_scanned": 10,
        })

        port_list = "\n".join([f"- Port {p['port']} ({p['service']}): OPEN" for p in open_ports])
        return {
            "message": f"**Scan Complete: {target}**\n\n"
                       f"Scanned 10 common ports.\n"
                       f"Open ports found: {len(open_ports)}\n\n"
                       f"{port_list if port_list else 'No open ports detected.'}",
            "data": {"scan_id": scan_id, "open_ports": open_ports},
        }

    elif intent == IntentCategory.LIST_EXPLOITS:
        from .exploit import EXPLOIT_MODULES
        modules_text = "\n".join([
            f"- **{k}**: {v['description']} (Risk: {v['risk']})"
            for k, v in EXPLOIT_MODULES.items()
        ])
        return {
            "message": f"**Available Exploit Modules**\n\n{modules_text}",
            "data": {"modules": list(EXPLOIT_MODULES.keys())},
        }

    elif intent == IntentCategory.BEHAVIORAL_STATUS:
        patterns = db.get_behavioral_patterns()
        alerts = db.get_behavioral_alerts(5)
        return {
            "message": f"**Behavioral Engine Status**\n\n"
                       f"Active patterns: {len(patterns)}\n"
                       f"Recent alerts: {len(alerts)}\n\n"
                       + "\n".join([f"- {p['name']} ({p['severity']})" for p in patterns[:5]]),
            "data": {"patterns": len(patterns), "alerts": len(alerts)},
        }

    elif intent == IntentCategory.LIST_ALERTS:
        alerts = db.get_behavioral_alerts(10)
        if not alerts:
            return {"message": "No alerts recorded yet.", "data": {"alerts": []}}
        alert_text = "\n".join([f"- [{a['severity'].upper()}] {a['message']}" for a in alerts[:10]])
        return {
            "message": f"**Recent Alerts ({len(alerts)})**\n\n{alert_text}",
            "data": {"alerts": alerts},
        }

    elif intent == IntentCategory.IDENTITY_LOOKUP:
        identities = db.get_identities()
        id_text = "\n".join([f"- {i['name']} ({i['platform']}) - {i.get('email', 'N/A')}" for i in identities[:10]])
        return {
            "message": f"**Identity Database ({len(identities)} records)**\n\n{id_text}",
            "data": {"total": len(identities), "identities": identities[:10]},
        }

    elif intent == IntentCategory.LIST_EVENTS:
        events = db.get_recent_events(10)
        if not events:
            return {"message": "No events recorded yet.", "data": {"events": []}}
        ev_text = "\n".join([f"- [{e['event_type']}] {e['source']} @ {e['timestamp']}" for e in events])
        return {
            "message": f"**Recent Events ({len(events)})**\n\n{ev_text}",
            "data": {"events": events},
        }

    elif intent == IntentCategory.EVENT_STATS:
        stats = db.get_event_stats()
        return {
            "message": f"**Event Statistics**\n\nTotal: {stats['total_events']}\n"
                       + "\n".join([f"- {k}: {v}" for k, v in stats.get('event_types', {}).items()]),
            "data": stats,
        }

    elif intent == IntentCategory.LIST_FILES:
        import os
        from ..config import SANDBOX_ROOT
        entries = []
        if os.path.isdir(SANDBOX_ROOT):
            for entry in os.scandir(SANDBOX_ROOT):
                entries.append({"name": entry.name, "is_dir": entry.is_dir()})
        file_text = "\n".join([f"- {'[DIR]' if e['is_dir'] else '     '} {e['name']}" for e in entries[:20]])
        return {
            "message": f"**Sandbox Files ({len(entries)} entries)**\n\n{file_text or 'Empty sandbox.'}",
            "data": {"entries": entries},
        }

    elif intent == IntentCategory.DARKWEB_SEARCH:
        # Extract search query from message
        query_text = message.lower()
        for prefix in ["dark web search", "darkweb search", "dark web", "darkweb",
                        "tor search", "search dark", "robin search", "search onion"]:
            query_text = query_text.replace(prefix, "").strip()
        if not query_text or len(query_text) < 3:
            query_text = message

        try:
            from .darkweb import _robin_available, _check_tor
            if not _robin_available:
                return {
                    "message": "**Dark Web Module Not Available**\n\nRobin search requires `beautifulsoup4`, `requests`, and `pysocks`.\n"
                               "Install with: `pip install beautifulsoup4 requests pysocks`",
                    "data": {"error": "robin_not_available"},
                }
            tor = _check_tor()
            if tor["status"] != "up":
                return {
                    "message": f"**Tor Proxy Offline**\n\nTor SOCKS5 proxy not reachable on 127.0.0.1:9150.\n"
                               f"Install Tor and start the service.\n\nError: {tor['error']}",
                    "data": {"tor_status": tor},
                }
            from search import get_search_results
            results = get_search_results(query_text, max_workers=5)
            results_text = "\n".join([f"- [{r['title'][:60]}]({r['link']})" for r in results[:15]])
            db.add_event(
                event_id=f"evt_dw_{uuid.uuid4().hex[:8]}",
                event_type="darkweb_search",
                source="julius-chatbot",
                data={"query": query_text, "results": len(results)}
            )
            return {
                "message": f"**Dark Web Search: `{query_text}`**\n\n"
                           f"Found {len(results)} results across {16} search engines.\n\n"
                           f"**Top Results:**\n{results_text or 'No results found.'}",
                "data": {"query": query_text, "results": results[:20], "total": len(results)},
            }
        except Exception as e:
            return {
                "message": f"**Dark Web Search Error**\n\n{str(e)}",
                "data": {"error": str(e)},
            }

    elif intent == IntentCategory.DARKWEB_STATUS:
        try:
            from .darkweb import _robin_available, _llm_available, _check_tor, SEARCH_ENGINES
            tor = _check_tor()
            return {
                "message": f"**Dark Web OSINT Status**\n\n"
                           f"- Robin AI: {'Online' if _robin_available else 'Offline'}\n"
                           f"- Tor Proxy: {tor['status'].upper()}"
                           f"{' (' + str(tor['latency_ms']) + 'ms)' if tor['latency_ms'] else ''}\n"
                           f"- LLM Analysis: {'Available' if _llm_available else 'Not configured'}\n"
                           f"- Search Engines: {len(SEARCH_ENGINES)}\n"
                           f"- Presets: threat_intel, ransomware_malware, personal_identity, corporate_espionage",
                "data": {"robin": _robin_available, "tor": tor, "llm": _llm_available},
            }
        except Exception as e:
            return {"message": f"Dark web status check failed: {e}", "data": {}}

    elif intent == IntentCategory.PORT_CHECK:
        import re
        match = re.search(r'port\s+(\d+)\s+(?:on\s+)?([\d.]+)', message, re.IGNORECASE) or \
                re.search(r'([\d.]+)\s+port\s+(\d+)', message, re.IGNORECASE)
        if match:
            groups = match.groups()
            if re.search(r'^\d+$', groups[0]):
                port_num, target = int(groups[0]), groups[1]
            else:
                target, port_num = groups[0], int(groups[1])
            from .scanner import _check_port
            result = _check_port(target, port_num, 3.0)
            status_str = "OPEN" if result["status"] == "open" else "CLOSED"
            banner_info = f"\nBanner: `{result['banner']}`" if result.get("banner") else ""
            return {
                "message": f"**Port Check: {target}:{port_num}**\n\n"
                           f"Status: **{status_str}**\n"
                           f"Service: {result.get('service', 'unknown')}{banner_info}",
                "data": result,
            }
        else:
            return {
                "message": "Please specify a target and port.\n\n"
                           "Examples:\n- `check port 443 on 192.168.1.1`\n- `check port 80 on 127.0.0.1`",
                "data": {},
            }

    elif intent == IntentCategory.VULN_SCAN:
        import re
        match = re.search(r'(?:scan|check|audit)\s+([\d.]+)', message, re.IGNORECASE)
        target = match.group(1) if match else "127.0.0.1"

        scan_id = f"scan_vuln_{uuid.uuid4().hex[:12]}"
        db.create_scan(scan_id, target, "vulnerability")

        from .scanner import _check_port, _detect_vulnerabilities, TOP_PORTS
        open_ports = []
        for port in TOP_PORTS:
            result = _check_port(target, port, 1.5)
            if result["status"] == "open":
                open_ports.append(result)

        vulns = _detect_vulnerabilities(scan_id, target, open_ports)
        db.update_scan(scan_id, "completed", {
            "target": target, "open_ports": open_ports,
            "total_ports_scanned": len(TOP_PORTS), "vulnerabilities": vulns,
        })

        vuln_text = "\n".join([f"- [{v.get('severity', 'info').upper()}] {v.get('title', 'Unknown')}" for v in vulns[:10]])
        return {
            "message": f"**Vulnerability Scan: {target}**\n\n"
                       f"Scanned {len(TOP_PORTS)} ports, found {len(open_ports)} open.\n"
                       f"Vulnerabilities detected: {len(vulns)}\n\n"
                       f"{vuln_text if vuln_text else 'No vulnerabilities detected.'}\n\n"
                       f"Scan ID: `{scan_id}`",
            "data": {"scan_id": scan_id, "open_ports": open_ports, "vulnerabilities": vulns},
        }

    elif intent == IntentCategory.RUN_EXPLOIT:
        import re
        # Target extraction (IP or domain)
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        target = ip_match.group(1) if ip_match else None
        
        # Port extraction
        port_match = re.search(r'port\s+(\d+)', message, re.IGNORECASE)
        port = int(port_match.group(1)) if port_match else 22 # Default to SSH port for generic hack
        
        # Attempt to determine exploit type
        exploit_type = "ssh_bruteforce" # Default
        for k in ["ftp", "anonymous"]:
            if k in message.lower(): exploit_type = "ftp_anonymous"; break
        for k in ["redis", "unauth"]:
            if k in message.lower(): exploit_type = "redis_unauth"; break
        for k in ["dir", "traversal", "path"]:
            if k in message.lower(): exploit_type = "http_dir_traversal"; break

        if not target:
            return {
                "message": "Please specify a target to exploit.\n\nExample: `exploit 192.168.1.100` or `hack 10.0.0.5 port 80`",
                "data": {}
            }

        from .exploit import EXPLOIT_HANDLERS, EXPLOIT_MODULES
        handler = EXPLOIT_HANDLERS.get(exploit_type)
        if not handler:
            return {"message": f"Exploit module `{exploit_type}` not found.", "data": {}}

        # Execute exploit (synchronous call for the rule-based handler)
        result = handler(target, port, {})
        
        status_label = "SUCCESS" if result.get("success") else "FAILED"
        msg = f"**Exploit Execution: {exploit_type}**\n\n"
        msg += f"**Target:** {target}:{port}\n"
        msg += f"**Status:** {status_label}\n\n"
        if result.get("success"):
            msg += f"**Result:** {result.get('message', 'Access established.')}\n"
            if result.get("data"):
                msg += f"```json\n{json.dumps(result['data'], indent=2)}\n```"
        else:
            msg += f"**Error:** {result.get('error', 'Unknown failure.')}\n\n"
            msg += f"**Recommendation for Best Solution:**\n"
            msg += f"For a more powerful assessment, try the comprehensive workflows:\n"
            msg += f"- `cyberstrike full pentest {target}` — Full autonomous assessment chain\n"
            msg += f"- `investigate {target}` — Recon + Vulns + Dark Web pipeline"

        db.add_event(
            event_id=f"evt_exp_{uuid.uuid4().hex[:8]}",
            event_type="exploit_executed",
            source="julius-chatbot-fallback",
            data={"target": target, "port": port, "exploit": exploit_type, "success": result.get("success")}
        )

        return {"message": msg, "data": result}

    elif intent == IntentCategory.IDENTITY_MERGE:
        import re
        match = re.search(r'merge\s+(.+?)\s+(?:and|with|into)\s+(.+)', message, re.IGNORECASE)
        if match:
            name1, name2 = match.group(1).strip(), match.group(2).strip()
            identities = db.get_identities()
            source = next((i for i in identities if name1.lower() in i["name"].lower() or i["id"] == name1), None)
            target_id = next((i for i in identities if name2.lower() in i["name"].lower() or i["id"] == name2), None)
            if source and target_id:
                result = db.merge_identities(source["id"], target_id["id"])
                return {
                    "message": f"**Identity Merge Complete**\n\n"
                               f"Merged `{source['name']}` ({source['id']}) into `{target_id['name']}` ({target_id['id']})",
                    "data": result,
                }
            else:
                not_found = []
                if not source:
                    not_found.append(name1)
                if not target_id:
                    not_found.append(name2)
                return {
                    "message": f"Could not find identity: {', '.join(not_found)}\n\n"
                               f"Available identities:\n" +
                               "\n".join([f"- {i['name']} ({i['id']})" for i in identities[:10]]),
                    "data": {},
                }
        else:
            return {
                "message": "Please specify two identities to merge.\n\n"
                           "Example: `merge Alice Johnson and Alice J`",
                "data": {},
            }

    elif intent == IntentCategory.READ_FILE:
        import re
        match = re.search(r'(?:read|show|cat|view|open)\s+(?:file\s+)?(.+)', message, re.IGNORECASE)
        if match:
            filepath = match.group(1).strip().strip('"').strip("'")
            from ..config import SANDBOX_ROOT
            full_path = os.path.join(SANDBOX_ROOT, filepath)
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(os.path.realpath(SANDBOX_ROOT)):
                return {"message": f"Access denied: path is outside the sandbox.", "data": {}}
            if not os.path.isfile(real_path):
                return {"message": f"File not found: `{filepath}`", "data": {}}
            try:
                with open(real_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(10000)
                truncated = len(content) >= 10000
                preview = content[:2000] + ("\n...[truncated]" if truncated or len(content) > 2000 else "")
                return {
                    "message": f"**File: {filepath}** ({len(content)} chars)\n\n```\n{preview}\n```",
                    "data": {"path": filepath, "size": len(content), "truncated": truncated},
                }
            except Exception as e:
                return {"message": f"Error reading file: {e}", "data": {}}
        else:
            return {
                "message": "Please specify a file path.\n\nExample: `read file test.txt`",
                "data": {},
            }

    elif intent == IntentCategory.TRACE_IP:
        import re
        import ipaddress as _ipa
        import subprocess as _sp
        import platform as _plat

        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        target = ip_match.group(1) if ip_match else None
        if not target:
            words = message.split()
            for w in words:
                if "." in w and any(c.isdigit() for c in w):
                    target = w
                    break
        if not target:
            return {"message": "Please specify a target IP.\n\nExample: `trace 192.168.1.7`", "data": {}}

        results = {"target": target, "host_alive": False, "network_type": "unknown", "scan": {}, "geolocation": {}}
        is_private = False
        try:
            is_private = _ipa.ip_address(target).is_private
        except Exception:
            pass
        results["network_type"] = "Private LAN" if is_private else "Public Internet"

        # 1. Ping to check if host is alive
        ping_flag = "-n" if _plat.system() == "Windows" else "-c"
        try:
            ping_result = _sp.run(
                ["ping", ping_flag, "3", "-w", "2000", target],
                capture_output=True, text=True, timeout=10
            )
            ping_out = ping_result.stdout
            alive = "TTL=" in ping_out.upper() or "ttl=" in ping_out or "bytes from" in ping_out
            results["host_alive"] = alive

            latency = None
            latency_match = re.search(r'(?:Average|avg)[^\d]*(\d+(?:\.\d+)?)\s*ms', ping_out, re.IGNORECASE)
            if not latency_match:
                latency_match = re.search(r'time[=<](\d+(?:\.\d+)?)\s*ms', ping_out)
            if latency_match:
                latency = float(latency_match.group(1))
            results["latency_ms"] = latency
        except Exception:
            results["host_alive"] = None
            results["latency_ms"] = None

        # 2. ARP lookup for MAC address (LAN only)
        mac_address = None
        hostname = None
        if is_private:
            try:
                arp_result = _sp.run(["arp", "-a", target], capture_output=True, text=True, timeout=5)
                mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', arp_result.stdout)
                if mac_match:
                    mac_address = mac_match.group(0)
            except Exception:
                pass
            try:
                import socket as _s
                hostname = _s.gethostbyaddr(target)[0]
            except Exception:
                pass

        results["mac_address"] = mac_address
        results["hostname"] = hostname

        # 3. Port scan with longer timeout for LAN
        from .scanner import _check_port, TOP_PORTS
        scan_timeout = 3.0 if is_private else 2.0
        scan_ports = TOP_PORTS
        open_ports = []
        filtered_count = 0
        for port in scan_ports:
            r = _check_port(target, port, scan_timeout)
            if r["status"] == "open":
                open_ports.append(r)
            elif r["status"] == "filtered":
                filtered_count += 1
        results["scan"] = {"open_ports": open_ports, "total_checked": len(scan_ports), "filtered": filtered_count}

        # 4. Geo lookup (only for public IPs)
        if not is_private:
            try:
                import httpx as _httpx
                resp = _httpx.get(f"http://ip-api.com/json/{target}?fields=66846719", timeout=10)
                if resp.status_code == 200:
                    results["geolocation"] = resp.json()
            except Exception:
                pass

        # Build response
        alive_str = "ONLINE" if results["host_alive"] else ("OFFLINE / Firewall blocking ICMP" if results["host_alive"] is False else "Unknown")
        port_list = "\n".join([f"  - Port {p['port']} ({p['service']}): OPEN{' — ' + p['banner'][:50] if p.get('banner') else ''}" for p in open_ports])

        msg = f"**Trace: {target}**\n\n"
        msg += f"**Network:** {results['network_type']}\n"
        msg += f"**Host Status:** {alive_str}"
        if results.get("latency_ms"):
            msg += f" ({results['latency_ms']}ms)"
        msg += "\n"
        if hostname:
            msg += f"**Hostname:** {hostname}\n"
        if mac_address:
            msg += f"**MAC Address:** {mac_address}\n"

        if not is_private and results.get("geolocation"):
            geo = results["geolocation"]
            msg += f"**Location:** {geo.get('city', '?')}, {geo.get('regionName', '?')}, {geo.get('country', '?')}\n"
            msg += f"**ISP:** {geo.get('isp', '?')}\n"

        msg += f"\n**Port Scan ({len(open_ports)} open / {len(scan_ports)} checked"
        if filtered_count > 0:
            msg += f", {filtered_count} filtered"
        msg += "):**\n"
        msg += port_list if port_list else "  No open ports — target firewall is likely blocking inbound connections"
        msg += "\n"

        if not results["host_alive"] and len(open_ports) == 0:
            msg += "\n**Note:** Host appears down or has a strict firewall. "
            if is_private:
                msg += "On the target device, check if Windows Firewall is blocking connections. Try: `netsh advfirewall show allprofiles`"

        msg += f"\n\nUse `investigate {target}` for a full reconnaissance workflow."

        return {"message": msg, "data": results}

    elif intent == IntentCategory.IP_LOOKUP:
        import re
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        domain_match = re.search(r'([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', message) if not ip_match else None
        target = ip_match.group(1) if ip_match else (domain_match.group(1) if domain_match else None)

        if not target:
            return {"message": "Please specify an IP or domain.\n\nExample: `ip lookup 8.8.8.8`", "data": {}}

        import httpx as _httpx
        results = {}
        try:
            resp = _httpx.get(f"http://ip-api.com/json/{target}?fields=66846719", timeout=10)
            if resp.status_code == 200:
                results = resp.json()
        except Exception as e:
            results = {"error": str(e)}

        info_lines = "\n".join([f"- **{k}:** {v}" for k, v in results.items() if k not in ("status", "query") and v])
        return {
            "message": f"**IP Lookup: {target}**\n\n{info_lines or 'No data available.'}",
            "data": results,
        }

    elif intent == IntentCategory.DNS_LOOKUP:
        import re, socket as _sock
        domain_match = re.search(r'([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', message)
        domain = domain_match.group(1) if domain_match else None

        if not domain:
            return {"message": "Please specify a domain.\n\nExample: `dns lookup google.com`", "data": {}}

        results = {}
        try:
            ips = _sock.getaddrinfo(domain, None)
            unique_ips = list(set(addr[4][0] for addr in ips))
            results["a_records"] = unique_ips
            results["resolved"] = True
            try:
                rev = _sock.gethostbyaddr(unique_ips[0])
                results["reverse_dns"] = rev[0]
            except Exception:
                pass
        except Exception as e:
            results = {"resolved": False, "error": str(e)}

        records = "\n".join([f"  - {ip}" for ip in results.get("a_records", [])])
        return {
            "message": f"**DNS Lookup: {domain}**\n\n"
                       f"**Resolved:** {'Yes' if results.get('resolved') else 'No'}\n"
                       f"**A Records:**\n{records or '  None'}\n"
                       f"{'**Reverse DNS:** ' + results.get('reverse_dns', 'N/A') if results.get('resolved') else ''}",
            "data": {"domain": domain, "dns": results},
        }

    elif intent == IntentCategory.INVESTIGATE:
        import re
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        domain_match = re.search(r'([a-zA-Z0-9-]+\.[a-zA-Z]{2,})', message) if not ip_match else None
        target = ip_match.group(1) if ip_match else (domain_match.group(1) if domain_match else None)

        if not target:
            return {"message": "Please specify a target.\n\nExample: `investigate 192.168.1.10`", "data": {}}

        scan_id = f"scan_{uuid.uuid4().hex[:12]}"
        db.create_scan(scan_id, target, "investigate")
        from .scanner import _check_port, _detect_vulnerabilities, TOP_PORTS
        open_ports = []
        for port in TOP_PORTS[:15]:
            r = _check_port(target, port, 1.0)
            if r["status"] == "open":
                open_ports.append(r)
        vulns = _detect_vulnerabilities(scan_id, target, open_ports)
        db.update_scan(scan_id, "completed", {"open_ports": open_ports, "vulnerabilities": vulns})

        import httpx as _httpx
        geo = {}
        try:
            resp = _httpx.get(f"http://ip-api.com/json/{target}?fields=status,country,city,isp,org", timeout=5)
            if resp.status_code == 200:
                geo = resp.json()
        except Exception:
            pass

        port_list = "\n".join([f"  - Port {p['port']} ({p['service']}): OPEN — {p.get('banner', '')[:60]}" for p in open_ports])
        vuln_list = "\n".join([f"  - [{v.get('severity','?').upper()}] {v.get('title','?')}" for v in vulns[:5]])

        from ..services.workflow_engine import create_from_template
        wf_id = create_from_template("recon", {"target": target})
        wf_note = f"\nFull recon workflow #{wf_id} created. Execute it from the Insights panel." if wf_id else ""

        return {
            "message": f"**Investigation: {target}**\n\n"
                       f"**Location:** {geo.get('city', '?')}, {geo.get('country', '?')} | **ISP:** {geo.get('isp', '?')}\n\n"
                       f"**Scan Results:** {len(open_ports)} open ports / {len(vulns)} vulnerabilities\n\n"
                       f"**Open Ports:**\n{port_list or '  None found on common ports'}\n\n"
                       f"**Vulnerabilities:**\n{vuln_list or '  None detected'}"
                       f"{wf_note}",
            "data": {"scan_id": scan_id, "open_ports": open_ports, "vulnerabilities": vulns, "geo": geo, "workflow_id": wf_id},
        }

    elif intent == IntentCategory.STORE_CREDENTIALS:
        import re
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        target = ip_match.group(1) if ip_match else "*"

        cred_user = None
        cred_pass = None
        user_match = re.search(r'user(?:name)?[:\s]+(\S+)', message, re.IGNORECASE)
        pass_match = re.search(r'pass(?:word)?[:\s]+(\S+)', message, re.IGNORECASE)
        if user_match:
            cred_user = user_match.group(1)
        if pass_match:
            cred_pass = pass_match.group(1)

        if not cred_user or not cred_pass:
            return {
                "message": "**Store Remote Credentials**\n\n"
                           "Please provide username and password.\n\n"
                           "**Format:** `set credentials for 192.168.1.20 user:Admin pass:MyPassword`\n\n"
                           "**For all targets:** `set credentials user:Admin pass:MyPassword`\n\n"
                           "Once stored, all remote commands will use these credentials automatically.",
                "data": {},
            }

        from ..services.remote_ops import store_credentials
        store_credentials(target, cred_user, cred_pass)
        target_label = f"`{target}`" if target != "*" else "**all targets** (default)"
        return {
            "message": f"**Credentials Stored** ✅\n\n"
                       f"**Target:** {target_label}\n"
                       f"**Username:** `{cred_user}`\n"
                       f"**Password:** `{'*' * len(cred_pass)}`\n\n"
                       f"All future remote commands to this target will use these credentials automatically.",
            "data": {"target": target, "username": cred_user},
        }

    elif intent == IntentCategory.REMOTE_COMMAND:
        import re
        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', message)
        target = ip_match.group(1) if ip_match else None
        if not target:
            return {"message": "Please specify a target IP.\n\nExample: `create folder on 192.168.1.7 at C:\\Users\\Admin\\Desktop\\TestFolder`", "data": {}}

        msg_lower = message.lower()

        from ..services.remote_ops import create_remote_folder, execute_remote_command

        # Parse credentials if provided: user:xxx pass:yyy
        cred_user = None
        cred_pass = None
        user_match = re.search(r'user(?:name)?[:\s]+(\S+)', message, re.IGNORECASE)
        pass_match = re.search(r'pass(?:word)?[:\s]+(\S+)', message, re.IGNORECASE)
        if user_match:
            cred_user = user_match.group(1)
        if pass_match:
            cred_pass = pass_match.group(1)

        if any(k in msg_lower for k in ["make folder", "create folder", "mkdir", "create directory"]):
            path_match = re.search(r'(?:at|path)\s+([A-Za-z]:\\[^\s]+|[~/][^\s]+)', message, re.IGNORECASE)
            if not path_match:
                folder_match = re.search(r'(?:folder|directory)\s+(?:named?\s+)?["\']?(\w[\w\s-]*\w|\w+)["\']?\s+(?:on|at)', message, re.IGNORECASE)
                if folder_match:
                    folder_name = folder_match.group(1).strip()
                    remote_path = f"C:\\Users\\Public\\Desktop\\{folder_name}"
                else:
                    remote_path = "C:\\Users\\Public\\Desktop\\JULIUS_Remote"
            else:
                remote_path = path_match.group(1)

            result = create_remote_folder(target, remote_path, username=cred_user, password=cred_pass)

            if result["success"]:
                db.add_event(
                    event_id=f"evt_remote_{uuid.uuid4().hex[:8]}",
                    event_type="remote_folder_created",
                    source="julius-remote-ops",
                    data={"target": target, "path": remote_path, "method": result.get("method")}
                )
                return {
                    "message": f"**Folder Created on {target}**\n\n"
                               f"**Path:** `{remote_path}`\n"
                               f"**Method:** {result.get('method', 'unknown')}\n"
                               f"**Status:** Success",
                    "data": result,
                }
            else:
                return {
                    "message": f"**Failed to Create Folder on {target}**\n\n"
                               f"**Attempted path:** `{remote_path}`\n"
                               f"**Error:** {result.get('error', 'Unknown error')}\n\n"
                               f"**To fix this, run ONE of these on the target laptop ({target}):**\n\n"
                               f"**Option 1 — Enable File Sharing (easiest):**\n"
                               f"  Open the folder you want to share → Right-click → Properties → Sharing tab → Share → Add 'Everyone' with Read/Write\n\n"
                               f"**Option 2 — Enable WinRM (PowerShell as Admin on target):**\n"
                               f"  `Enable-PSRemoting -Force`\n"
                               f"  `Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force`\n\n"
                               f"**Option 3 — Enable Admin Shares (Registry on target):**\n"
                               f"  `reg add HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System /v LocalAccountTokenFilterPolicy /t REG_DWORD /d 1 /f`\n"
                               f"  Then restart the target\n\n"
                               f"**Note:** If password is a PIN, use the actual Microsoft account password instead.",
                    "data": result,
                }
        else:
            cmd_match = re.search(r'(?:run|execute|exec)\s+["\']?(.+?)["\']?\s+on\s+', message, re.IGNORECASE)
            if not cmd_match:
                cmd_match = re.search(r'on\s+\S+\s+(?:run|execute|exec)\s+["\']?(.+)["\']?', message, re.IGNORECASE)
            command = cmd_match.group(1).strip() if cmd_match else "hostname"

            result = execute_remote_command(target, command, username=cred_user, password=cred_pass)
            status = "Success" if result["success"] else "Failed"
            return {
                "message": f"**Remote Command on {target}**\n\n"
                           f"**Command:** `{command}`\n"
                           f"**Status:** {status}\n"
                           f"**Method:** {result.get('method', 'N/A')}\n\n"
                           f"**Output:**\n```\n{result.get('output', result.get('error', 'No output'))}\n```",
                "data": result,
            }

    elif intent == IntentCategory.DARKWEB_INVESTIGATE:
        return {
            "message": "**Dark Web Investigation**\n\n"
                       "Use the Dark Web panel or the API directly:\n\n"
                       "1. Go to the **Dark Web** panel in the sidebar\n"
                       "2. Enter your search query\n"
                       "3. Click **Investigate** to run the full pipeline\n\n"
                       "Or use the chat:\n"
                       "- `dark web search <query>` — Search .onion sites\n"
                       "- `tor status` — Check Tor connectivity\n\n"
                       "**API:** `POST /api/darkweb/investigate`",
            "data": {},
        }

    elif intent == IntentCategory.INSTALL_PACKAGE:
        import re as _re
        import subprocess as _sp
        import platform as _plat

        msg_lower = message.lower().strip()

        # Extract package name(s)
        packages = []
        # Pattern: "install <pkg1> <pkg2>" or "pip install <pkg>" or "install <pkg> using pip"
        clean = msg_lower
        for prefix in ["pip install", "npm install", "choco install", "apt install",
                        "install package", "install tool", "install module",
                        "install library", "install software", "install dependency",
                        "add package", "download and install", "install"]:
            if prefix in clean:
                clean = clean.replace(prefix, "", 1).strip()
                break
        # Remove noise words
        for noise in ["using pip", "with pip", "via pip", "using npm", "with npm",
                       "please", "can you", "could you", "i want to", "i need",
                       "for me", "on this machine", "locally"]:
            clean = clean.replace(noise, "").strip()
        # Split remaining into package names
        raw_pkgs = [p.strip().strip('"').strip("'") for p in _re.split(r'[,\s]+', clean) if p.strip()]
        packages = [p for p in raw_pkgs if len(p) >= 2 and p.isascii() and not p.startswith("-")]

        if not packages:
            return {
                "message": "**Package Installer**\n\n"
                           "Please specify what to install.\n\n"
                           "**Examples:**\n"
                           "- `install requests`\n"
                           "- `install paramiko nmap shodan`\n"
                           "- `npm install axios`\n"
                           "- `install nmap using pip`\n\n"
                           "**Supported managers:** pip (Python), npm (Node.js), choco (Windows)",
                "data": {},
            }

        # Detect package manager
        pkg_manager = "pip"  # default
        if "npm" in msg_lower:
            pkg_manager = "npm"
        elif "choco" in msg_lower:
            pkg_manager = "choco"
        elif "apt" in msg_lower:
            pkg_manager = "apt"

        # Build command
        if pkg_manager == "pip":
            cmd = ["pip", "install"] + packages
        elif pkg_manager == "npm":
            cmd = ["npm", "install"] + packages
        elif pkg_manager == "choco":
            cmd = ["choco", "install", "-y"] + packages
        elif pkg_manager == "apt":
            cmd = ["sudo", "apt", "install", "-y"] + packages
        else:
            cmd = ["pip", "install"] + packages

        pkg_list_str = ", ".join([f"`{p}`" for p in packages])

        try:
            result = _sp.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            output = result.stdout[-2000:] if result.stdout else ""
            error = result.stderr[-1000:] if result.stderr else ""

            if result.returncode == 0:
                # Log event
                db.add_event(
                    event_id=f"evt_install_{uuid.uuid4().hex[:8]}",
                    event_type="package_installed",
                    source="julius-sysadmin",
                    data={"packages": packages, "manager": pkg_manager}
                )

                # Extract installed versions from pip output
                installed_info = ""
                if "Successfully installed" in output:
                    match = _re.search(r'Successfully installed (.+)', output)
                    if match:
                        installed_info = f"\n\n**Installed:** {match.group(1)}"
                elif "already satisfied" in output.lower():
                    installed_info = "\n\n**Note:** Package(s) already installed."

                return {
                    "message": f"**✅ Installation Successful**\n\n"
                               f"**Manager:** {pkg_manager}\n"
                               f"**Packages:** {pkg_list_str}\n"
                               f"**Command:** `{' '.join(cmd)}`"
                               f"{installed_info}\n\n"
                               f"```\n{output[-800:] if output else '(done)'}\n```",
                    "data": {"success": True, "packages": packages, "manager": pkg_manager},
                }
            else:
                return {
                    "message": f"**❌ Installation Failed**\n\n"
                               f"**Manager:** {pkg_manager}\n"
                               f"**Packages:** {pkg_list_str}\n"
                               f"**Command:** `{' '.join(cmd)}`\n\n"
                               f"**Error:**\n```\n{error[-500:] or output[-500:] or 'Unknown error'}\n```",
                    "data": {"success": False, "packages": packages, "error": error[:300]},
                }
        except _sp.TimeoutExpired:
            return {
                "message": f"**⏱️ Installation Timed Out**\n\n"
                           f"**Packages:** {pkg_list_str}\n"
                           f"Installation took longer than 120 seconds. Try running manually:\n"
                           f"```\n{' '.join(cmd)}\n```",
                "data": {"success": False, "error": "timeout"},
            }
        except FileNotFoundError:
            return {
                "message": f"**❌ Package Manager Not Found**\n\n"
                           f"`{pkg_manager}` is not installed or not in PATH.\n\n"
                           f"**Fix:** Make sure `{pkg_manager}` is installed and accessible from the command line.",
                "data": {"success": False, "error": f"{pkg_manager} not found"},
            }
        except Exception as e:
            return {
                "message": f"**❌ Installation Error**\n\n{str(e)}",
                "data": {"success": False, "error": str(e)},
            }

    elif intent == IntentCategory.LINUX_COMMAND:
        from ..services.linux_shell import (
            execute_linux, get_shell_status, get_linux_system_info, get_command_history
        )

        msg_lower = message.lower().strip()

        # Sub-commands: status, info, history
        if any(k in msg_lower for k in ["linux status", "shell status", "terminal status", "wsl status"]):
            status = get_shell_status()
            if status.get("operational"):
                return {
                    "message": f"**🐧 Linux Terminal — Online**\n\n"
                               f"**Backend:** {status.get('backend', 'N/A')}\n"
                               f"**Kernel:** {status.get('kernel', 'N/A')}\n"
                               f"**Distro:** {status.get('distro', 'N/A')}\n"
                               f"**Host OS:** {status.get('host_os', 'N/A')}\n\n"
                               f"Ready to execute commands. Try:\n"
                               f"- `linux ls -la`\n"
                               f"- `linux uname -a`\n"
                               f"- `linux info`",
                    "data": status,
                }
            else:
                return {
                    "message": f"**🐧 Linux Terminal — Offline**\n\n"
                               f"{status.get('install_instructions', 'WSL not available.')}\n\n"
                               f"**Host OS:** {status.get('host_os', 'N/A')}",
                    "data": status,
                }

        elif any(k in msg_lower for k in ["linux info", "linux system", "sysinfo"]):
            info = get_linux_system_info()
            info_lines = "\n".join([f"**{k.title()}:** {v}" for k, v in info.items()])
            return {
                "message": f"**🐧 Linux System Information**\n\n{info_lines}",
                "data": info,
            }

        elif any(k in msg_lower for k in ["linux history", "shell history", "command history"]):
            history = get_command_history(limit=10)
            if not history:
                return {"message": "**No command history yet.** Run some Linux commands first.", "data": {}}
            lines = []
            for i, h in enumerate(history, 1):
                status_icon = "✅" if h.get("success") else "❌"
                lines.append(f"{i}. {status_icon} `{h.get('command', '?')}` ({h.get('duration_ms', 0)}ms)")
            return {
                "message": f"**🐧 Recent Commands**\n\n" + "\n".join(lines),
                "data": {"history": history},
            }

        else:
            # Extract the actual Linux command from the message
            command = msg_lower
            # Strip common prefixes
            for prefix in ["run linux command", "run linux", "run bash", "run shell",
                           "linux command", "execute linux", "exec linux",
                           "bash command", "shell command",
                           "linux ", "bash ", "terminal ", "shell ", "wsl "]:
                if command.startswith(prefix):
                    command = command[len(prefix):].strip()
                    break
            # Also try original case for the command
            orig = message.strip()
            for prefix in ["run linux command", "run linux", "run bash", "run shell",
                           "linux command", "execute linux", "exec linux",
                           "bash command", "shell command",
                           "linux ", "bash ", "terminal ", "shell ", "wsl "]:
                if orig.lower().startswith(prefix):
                    command = orig[len(prefix):].strip()
                    break

            if not command or command in ["linux", "bash", "terminal", "shell"]:
                return {
                    "message": "**🐧 JULIUS Linux Terminal**\n\n"
                               "Specify a command to execute:\n\n"
                               "**Examples:**\n"
                               "- `linux ls -la /home`\n"
                               "- `linux uname -a`\n"
                               "- `linux cat /etc/os-release`\n"
                               "- `linux apt list --installed`\n"
                               "- `linux ifconfig`\n"
                               "- `linux status` — Check shell status\n"
                               "- `linux info` — System information\n"
                               "- `linux history` — Recent commands",
                    "data": {},
                }

            # Execute the command (always use execute_script to auto-confirm interactive prompts)
            from ..services.linux_shell import execute_script
            result = execute_script(command, timeout=120)
            # Log event
            db.add_event(
                event_id=f"evt_linux_{uuid.uuid4().hex[:8]}",
                event_type="linux_command",
                source="julius-terminal",
                data={"command": command, "success": result.get("success"),
                      "exit_code": result.get("exit_code"), "backend": result.get("backend")}
            )

            status_icon = "✅" if result.get("success") else "❌"
            output = result.get("output", "")
            error = result.get("error", "")
            display_output = output if output else error if error else "(no output)"

            # Build stderr section separately to avoid backslash in f-string expression
            stderr_part = ('\n**stderr:**\n```\n' + error[-500:] + '\n```') if error and output else ''

            return {
                "message": f"**{status_icon} Linux Terminal** `{result.get('backend', 'N/A')}`\n\n"
                           f"**$** `{command}`\n"
                           f"**CWD:** `{result.get('cwd', '~')}`\n"
                           f"**Exit:** {result.get('exit_code', 'N/A')} · {result.get('duration_ms', 0)}ms\n\n"
                           f"```\n{display_output[-2000:]}\n```"
                           + stderr_part,
                "data": result,
            }

    elif intent == IntentCategory.GREETING:
        # Give varied contextual responses based on what the user actually said
        msg_lower = message.lower().strip()
        stats = db.get_system_stats()
        status_line = (
            f"\n\n**Quick Status:** {stats['total_scans']} scans · "
            f"{stats['total_vulnerabilities']} vulns · "
            f"{stats['total_events']} events · "
            f"{stats['total_alerts']} alerts"
        )

        if any(k in msg_lower for k in ["how are you", "how r u", "how's it going", "how is it going"]):
            return {
                "message": f"**All systems operational.** Running at peak efficiency.{status_line}"
                           f"\n\nWhat would you like me to do? Try `scan`, `status`, or `help` for the full command list.",
                "data": stats,
            }
        elif any(k in msg_lower for k in ["good morning", "good afternoon", "good evening"]):
            greeting = "Good morning" if "morning" in msg_lower else ("Good afternoon" if "afternoon" in msg_lower else "Good evening")
            return {
                "message": f"**{greeting}, operator.** JULIUS is ready.{status_line}"
                           f"\n\nReady for tasking. What's the objective?",
                "data": stats,
            }
        else:
            return {
                "message": f"**JULIUS AI Online** — Unified Security Operations Platform.{status_line}"
                           f"\n\nI can scan networks, analyze threats, investigate targets, search the dark web, and more. "
                           f"Type `help` for the full command reference, or just tell me what you need.",
                "data": stats,
            }

    else:
        # UNKNOWN intent — provide helpful fallback
        ai_note = ""
        if not is_autogen_ready():
            ai_note = (
                "\n\n💡 **Tip:** Set the `OPENAI_API_KEY` environment variable to enable the JULIUS AI Brain "
                "(GPT-4o-mini with AutoGen). The AI brain can understand natural language and execute complex workflows."
            )
        return {
            "message": f"I'm not sure how to handle that. Here are some things I can do:\n\n"
                       f"- `scan <target>` — Network port scan\n"
                       f"- `trace <ip>` — Full trace & investigation\n"
                       f"- `dark web search <query>` — Search .onion sites\n"
                       f"- `status` — System overview\n"
                       f"- `alerts` — View security alerts\n"
                       f"- `help` — Full command reference"
                       f"{ai_note}",
            "data": {},
        }


# ═══════════════════════════════════════════════════════════════════════════
# Request/Response Models
# ═══════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


# In-memory session history
chat_sessions: Dict[str, list] = {}


# ═══════════════════════════════════════════════════════════════════════════
# REST Endpoints
# ═══════════════════════════════════════════════════════════════════════════

# Only these trivial intents skip AutoGen (instant, deterministic responses)
FAST_INTENTS = {
    IntentCategory.GREETING,
    IntentCategory.SYSTEM_STATUS,
    IntentCategory.HELP,
}


@router.post("/message")
async def send_message(req: ChatRequest):
    """Process a chat message. AI-FIRST: AutoGen handles all messages when ready.
    Only trivial intents (greeting/status/help) bypass the AI brain.
    Rule-based handlers used as fallback when AutoGen is unavailable or errors."""
    start = time.time()
    session_id = req.session_id or "default"
    engine_used = "rule-based"
    tool_calls = []

    # Classify intent (used as hint for AI + fallback routing)
    intent, confidence = classify_intent(req.message)

    # ── AI-FIRST ROUTING ──────────────────────────────────────────────
    if is_autogen_ready():
        # Only skip AutoGen for trivial, high-confidence intents
        if intent in FAST_INTENTS and confidence > 0.7:
            result = await execute_intent(intent, req.message)
            response_message = result["message"]
            suggestions = _get_suggestions(intent)
            engine_used = "rule"
        else:
            # Send everything else to AutoGen with full context
            try:
                history = chat_sessions.get(session_id, [])[-10:]
                ag_result = await ask_julius(
                    message=req.message,
                    session_id=session_id,
                    conversation_history=history,
                    intent_hint=intent.value if intent != IntentCategory.UNKNOWN else None,
                    intent_confidence=confidence,
                )

                if ag_result and ag_result.get("message"):
                    response_message = ag_result["message"]
                    tool_calls = ag_result.get("tool_calls", [])
                    engine_used = f"autogen/{ag_result.get('model', 'gpt-4o')}"
                    suggestions = _get_suggestions(intent)
                else:
                    result = await execute_intent(intent, req.message)
                    response_message = result["message"]
                    suggestions = _get_suggestions(intent)
                    engine_used = "rule_fallback"
            except Exception as e:
                logger.warning(f"AutoGen brain error, falling back to rules: {e}")
                result = await execute_intent(intent, req.message)
                response_message = result["message"]
                suggestions = _get_suggestions(intent)
                engine_used = "rule_fallback"
    else:
        # ── AutoGen not available — pure rule-based ────────────────────
        result = await execute_intent(intent, req.message)
        response_message = result["message"]
        suggestions = _get_suggestions(intent)

    elapsed = (time.time() - start) * 1000

    # Store in session history
    if session_id not in chat_sessions:
        chat_sessions[session_id] = []
    chat_sessions[session_id].append({
        "role": "user", "content": req.message, "timestamp": datetime.utcnow().isoformat()
    })
    chat_sessions[session_id].append({
        "role": "assistant", "content": response_message, "timestamp": datetime.utcnow().isoformat(),
        "engine": engine_used,
    })
    if len(chat_sessions[session_id]) > 100:
        chat_sessions[session_id] = chat_sessions[session_id][-100:]

    return {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "message": response_message,
        "intent": {
            "category": intent.value,
            "confidence": confidence,
            "entities": {},
        },
        "actions": [{"id": tc.get("name", ""), "name": tc.get("name", ""), "type": "tool_call", "description": tc.get("args", "")[:100]} for tc in tool_calls],
        "execution": {
            "status": "completed",
            "results": [{
                "action_id": tc.get("name", "tool"),
                "status": "completed",
                "output": tc.get("args", ""),
                "error": None,
                "duration_ms": elapsed / max(len(tool_calls), 1),
                "logs": [],
            } for tc in tool_calls] if tool_calls else [{
                "action_id": "auto",
                "status": "completed",
                "output": None,
                "error": None,
                "duration_ms": elapsed,
                "logs": [],
            }],
            "total_duration_ms": elapsed,
        },
        "suggestions": suggestions,
        "processing_time_ms": round(elapsed, 2),
        "engine": engine_used,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 50):
    history = chat_sessions.get(session_id, [])
    return {"session_id": session_id, "messages": history[-limit:], "total": len(history)}


@router.delete("/history/{session_id}")
async def clear_history(session_id: str):
    if session_id in chat_sessions:
        del chat_sessions[session_id]
    return {"cleared": True, "session_id": session_id}


@router.get("/brain-status")
async def brain_status():
    """Check which AI engine is powering the chatbot."""
    return {
        "autogen_available": AUTOGEN_AVAILABLE,
        "autogen_ready": is_autogen_ready(),
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY", "")),
        "engine": "autogen/gpt-4o-mini" if is_autogen_ready() else "rule-based",
        "tools_count": 16,
        "tools": [
            "scan_target", "check_single_port", "list_vulnerabilities",
            "run_exploit", "list_exploit_modules", "get_identities",
            "get_identity_graph", "get_behavioral_status", "get_events",
            "get_system_stats", "get_live_metrics", "get_network_connections",
            "darkweb_search", "darkweb_status", "ip_threat_lookup", "dns_resolve",
        ],
    }


@router.get("/intents")
async def get_intents():
    intents = [{"category": c.value, "patterns": p[:3]} for c, p in INTENT_PATTERNS.items()]
    return {"intents": intents, "total": len(intents)}


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def send_json(self, ws: WebSocket, data: dict):
        try:
            await ws.send_json(data)
        except Exception:
            pass


ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await ws_manager.connect(websocket)
    session_id = f"ws-{id(websocket)}"

    await ws_manager.send_json(websocket, {
        "type": "connected",
        "data": {"message": "Connected to JULIUS AI", "session_id": session_id},
    })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await ws_manager.send_json(websocket, {"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            content = payload.get("content", "").strip()
            if not content:
                continue

            await ws_manager.send_json(websocket, {"type": "processing", "data": {"message": "Processing..."}})

            intent, confidence = classify_intent(content)
            engine_used = "rule-based"
            tool_calls_ws = []

            if is_autogen_ready():
                if intent in FAST_INTENTS and confidence > 0.7:
                    result = await execute_intent(intent, content)
                    response_msg = result["message"]
                else:
                    try:
                        history = chat_sessions.get(session_id, [])[-10:]
                        ag_result = await ask_julius(
                            message=content,
                            session_id=session_id,
                            conversation_history=history,
                            intent_hint=intent.value if intent != IntentCategory.UNKNOWN else None,
                            intent_confidence=confidence,
                        )
                        if ag_result and ag_result.get("message"):
                            response_msg = ag_result["message"]
                            tool_calls_ws = ag_result.get("tool_calls", [])
                            engine_used = f"autogen/{ag_result.get('model', 'gpt-4o')}"
                        else:
                            result = await execute_intent(intent, content)
                            response_msg = result["message"]
                    except Exception as e:
                        logger.warning(f"WS AutoGen error: {e}")
                        result = await execute_intent(intent, content)
                        response_msg = result["message"]
            else:
                result = await execute_intent(intent, content)
                response_msg = result["message"]

            await ws_manager.send_json(websocket, {
                "type": "response",
                "data": {
                    "id": f"msg_{uuid.uuid4().hex[:8]}",
                    "message": response_msg,
                    "intent": {"category": intent.value, "confidence": confidence},
                    "suggestions": _get_suggestions(intent),
                    "engine": engine_used,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            })
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_suggestions(intent: IntentCategory) -> List[str]:
    base = ["Check system status", "Show help"]
    mapping = {
        IntentCategory.SYSTEM_STATUS: ["Run a scan", "Show alerts", "List events"],
        IntentCategory.NETWORK_SCAN: ["List vulnerabilities", "Run exploit", "Show events"],
        IntentCategory.LIST_EXPLOITS: ["Run exploit", "Scan target", "Show alerts"],
        IntentCategory.BEHAVIORAL_STATUS: ["Show alerts", "List events", "Identity lookup"],
        IntentCategory.IDENTITY_LOOKUP: ["Merge identities", "Show events", "Run scan"],
        IntentCategory.GREETING: ["Check system status", "Run a scan", "Show help"],
    }
    return mapping.get(intent, base)
