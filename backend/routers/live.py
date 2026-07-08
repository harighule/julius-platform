"""
JULIUS Live Data Router — Real system metrics, network connections, threat feeds.
No simulation. All data comes from the actual running system + free public APIs.
"""

import logging
import socket
import platform
import time
import os
import json
import uuid
import threading
import ipaddress
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor

import psutil
import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/live", tags=["Live Data"])

_boot = time.time()

# ═══════════════════════════════════════════════════════════════════════════
# 1. REAL SYSTEM METRICS (psutil)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/metrics")
async def system_metrics():
    """Real-time system metrics from this machine."""
    cpu_freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net_io = psutil.net_io_counters()
    boot = datetime.fromtimestamp(psutil.boot_time())

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "host": {
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "arch": platform.machine(),
            "python": platform.python_version(),
            "boot_time": boot.isoformat(),
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
        },
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.5),
            "per_core": psutil.cpu_percent(interval=0, percpu=True),
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "freq_mhz": round(cpu_freq.current, 0) if cpu_freq else None,
        },
        "memory": {
            "total_gb": round(mem.total / (1024**3), 2),
            "used_gb": round(mem.used / (1024**3), 2),
            "available_gb": round(mem.available / (1024**3), 2),
            "percent": mem.percent,
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "free_gb": round(disk.free / (1024**3), 2),
            "percent": round(disk.percent, 1),
        },
        "network": {
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
            "errors_in": net_io.errin,
            "errors_out": net_io.errout,
            "mb_sent": round(net_io.bytes_sent / (1024**2), 2),
            "mb_recv": round(net_io.bytes_recv / (1024**2), 2),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. REAL NETWORK CONNECTIONS
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/connections")
async def active_connections():
    """Real active network connections on this machine."""
    conns = []
    for c in psutil.net_connections(kind="inet"):
        try:
            entry = {
                "fd": c.fd,
                "family": "IPv4" if c.family == socket.AF_INET else "IPv6",
                "type": "TCP" if c.type == socket.SOCK_STREAM else "UDP",
                "local_addr": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else None,
                "remote_addr": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else None,
                "status": c.status if hasattr(c, 'status') else "N/A",
                "pid": c.pid,
            }
            # Resolve process name
            if c.pid:
                try:
                    proc = psutil.Process(c.pid)
                    entry["process"] = proc.name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    entry["process"] = "unknown"
            else:
                entry["process"] = None
            conns.append(entry)
        except Exception:
            continue

    # Stats
    status_counts = {}
    for c in conns:
        s = c.get("status", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "connections": conns[:200],
        "total": len(conns),
        "status_distribution": status_counts,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/interfaces")
async def network_interfaces():
    """Real network interfaces and their addresses."""
    ifaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for name, addr_list in addrs.items():
        iface = {
            "name": name,
            "is_up": stats[name].isup if name in stats else False,
            "speed_mbps": stats[name].speed if name in stats else 0,
            "mtu": stats[name].mtu if name in stats else 0,
            "addresses": [],
        }
        for addr in addr_list:
            iface["addresses"].append({
                "family": str(addr.family.name) if hasattr(addr.family, 'name') else str(addr.family),
                "address": addr.address,
                "netmask": addr.netmask,
                "broadcast": addr.broadcast,
            })
        ifaces.append(iface)

    return {"interfaces": ifaces, "total": len(ifaces)}


@router.get("/processes")
async def running_processes():
    """Top processes by CPU/memory usage."""
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'username']):
        try:
            info = p.info
            if info['cpu_percent'] is not None and info['cpu_percent'] > 0:
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu_percent": round(info['cpu_percent'], 1),
                    "memory_percent": round(info['memory_percent'] or 0, 1),
                    "status": info['status'],
                    "user": info['username'],
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x['cpu_percent'], reverse=True)
    return {"processes": procs[:50], "total_system": len(list(psutil.process_iter()))}


# ═══════════════════════════════════════════════════════════════════════════
# 3. FREE THREAT INTELLIGENCE FEEDS
# ═══════════════════════════════════════════════════════════════════════════

_threat_cache: Dict[str, Any] = {}
_cache_ttl = 300  # 5 min
_latest_live_results: Dict[str, Any] = {
    "ip_lookup": None,
    "dns_lookup": None,
    "cves": None,
}


def get_live_report_snapshot() -> Dict[str, Any]:
    if not _latest_live_results.get("ip_lookup"):
        _latest_live_results["ip_lookup"] = db.get_live_tool_result("ip_lookup")
    if not _latest_live_results.get("dns_lookup"):
        _latest_live_results["dns_lookup"] = db.get_live_tool_result("dns_lookup")
    if not _latest_live_results.get("cves"):
        _latest_live_results["cves"] = db.get_live_tool_result("cves")

    return {
        "ip_lookup": _latest_live_results.get("ip_lookup"),
        "dns_lookup": _latest_live_results.get("dns_lookup"),
        "cves": _latest_live_results.get("cves"),
    }


async def _fetch_latest_cves_payload() -> Dict[str, Any]:
    cache_key = "nvd_latest"
    if cache_key in _threat_cache and time.time() - _threat_cache[cache_key]["ts"] < _cache_ttl:
        return _threat_cache[cache_key]["data"]

    url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    end = datetime.utcnow()
    start = end - timedelta(days=120)
    pub_start = start.strftime('%Y-%m-%dT%H:%M:%S.000')
    pub_end = end.strftime('%Y-%m-%dT%H:%M:%S.000')
    params = {"pubStartDate": pub_start, "pubEndDate": pub_end, "resultsPerPage": 40, "startIndex": 0}

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as exc:
        logger.warning("NVD fetch timed out: %s", exc)
        raise HTTPException(status_code=504, detail="Timed out while fetching live CVEs") from exc
    except httpx.HTTPStatusError as exc:
        logger.warning("NVD returned error %s", exc.response.status_code)
        raise HTTPException(status_code=502, detail="Live CVE provider returned an error") from exc
    except httpx.RequestError as exc:
        logger.warning("NVD request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Unable to reach the live CVE provider") from exc

    cves = []
    for item in data.get("vulnerabilities", [])[:40]:
        cve = item.get("cve", {})
        published = cve.get("published")
        published_date = None
        if published:
            try:
                published_date = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
            except ValueError:
                published_date = None
        if not published_date or published_date < start:
            continue

        desc_list = cve.get("descriptions", [])
        desc = next((d["value"] for d in desc_list if d.get("lang") == "en"), "No description")

        metrics = cve.get("metrics", {})
        cvss_score = None
        severity = "unknown"
        for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
            metric_entries = metrics.get(key) or []
            if not metric_entries:
                continue
            metric = metric_entries[0]
            cvss_data = metric.get("cvssData", {})
            cvss_score = cvss_data.get("baseScore")
            severity = (cvss_data.get("baseSeverity") or metric.get("baseSeverity") or "unknown").lower()
            break

        cves.append({
            "id": cve.get("id"),
            "description": desc[:300],
            "published": published,
            "severity": severity,
            "cvss_score": cvss_score,
            "last_modified": cve.get("lastModified"),
            "source": cve.get("sourceIdentifier"),
        })

    if not cves:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url, params={"resultsPerPage": 20})
                resp.raise_for_status()
                data = resp.json()
        except httpx.RequestError as exc:
            logger.warning("NVD fallback request failed: %s", exc)
        else:
            fallback_cves = []
            for item in data.get("vulnerabilities", [])[:20]:
                cve = item.get("cve", {})
                published = cve.get("published")
                if not published or str(published) < "2020":
                    continue
                desc_list = cve.get("descriptions", [])
                desc = next((d["value"] for d in desc_list if d.get("lang") == "en"), "No description")
                metrics = cve.get("metrics", {})
                cvss_score = None
                severity = "unknown"
                for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    metric_entries = metrics.get(key) or []
                    if not metric_entries:
                        continue
                    metric = metric_entries[0]
                    cvss_data = metric.get("cvssData", {})
                    cvss_score = cvss_data.get("baseScore")
                    severity = (cvss_data.get("baseSeverity") or metric.get("baseSeverity") or "unknown").lower()
                    break
                fallback_cves.append({
                    "id": cve.get("id"),
                    "description": desc[:300],
                    "published": published,
                    "severity": severity,
                    "cvss_score": cvss_score,
                    "last_modified": cve.get("lastModified"),
                    "source": cve.get("sourceIdentifier"),
                })
            cves = [c for c in fallback_cves if c.get("published", "") >= "2020"]

    cves.sort(key=lambda x: datetime.fromisoformat(str(x.get("published")).replace("Z", "+00:00")) if x.get("published") else datetime.min, reverse=True)

    result = {
        "cves": cves,
        "total_results": data.get("totalResults", 0),
        "fetched_at": datetime.utcnow().isoformat(),
    }
    _threat_cache[cache_key] = {"data": result, "ts": time.time()}
    _latest_live_results["cves"] = result
    try:
        db.save_live_tool_result("cves", result)
        db.add_event(
            event_id=f"evt_cves_{uuid.uuid4().hex[:8]}",
            event_type="cve_fetch",
            source="julius-tools",
            data={"result": result},
        )
    except Exception:
        pass
    return result


async def _lookup_ip_payload(ip_address: str) -> Dict[str, Any]:
    import re as _re
    import subprocess as _sp

    try:
        parsed_ip = ipaddress.ip_address(ip_address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid IP address") from exc

    results: Dict[str, Any] = {}
    payload = {
        "ip": ip_address,
        "country": None,
        "city": None,
        "org": None,
        "lat": None,
        "lon": None,
    }
    is_private = parsed_ip.is_private
    results["network_type"] = "Private LAN" if is_private else "Public Internet"

    if is_private:
        ping_flag = "-n" if platform.system() == "Windows" else "-c"
        try:
            pr = _sp.run(
                ["ping", ping_flag, "2", "-w", "1500", ip_address],
                capture_output=True,
                text=True,
                timeout=8,
            )
            alive = "TTL=" in pr.stdout.upper() or "ttl=" in pr.stdout or "bytes from" in pr.stdout
            results["host_alive"] = alive
            lat = _re.search(r"time[=<](\d+(?:\.\d+)?)\s*ms", pr.stdout)
            results["latency_ms"] = float(lat.group(1)) if lat else None
        except Exception:
            results["host_alive"] = None

        try:
            results["hostname"] = socket.gethostbyaddr(ip_address)[0]
        except Exception:
            results["hostname"] = None

        try:
            arp = _sp.run(["arp", "-a", ip_address], capture_output=True, text=True, timeout=5)
            mac = _re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", arp.stdout)
            results["mac_address"] = mac.group(0) if mac else None
        except Exception:
            results["mac_address"] = None

        if results.get("mac_address"):
            prefix = results["mac_address"].replace("-", ":").upper()[:8]
            try:
                async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                    resp = await client.get(f"https://api.macvendors.com/{prefix}")
                    results["device_vendor"] = resp.text if resp.status_code == 200 else None
            except Exception:
                results["device_vendor"] = None

        open_ports = []
        for port in [22, 80, 135, 139, 443, 445, 3389, 8080]:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.settimeout(1.0)
                    if probe.connect_ex((ip_address, port)) == 0:
                        open_ports.append(port)
            except Exception:
                pass
        results["open_ports"] = open_ports

        payload["country"] = "Local Network"
        payload["city"] = "LAN"
        payload["org"] = results.get("device_vendor") or results.get("hostname") or "LAN Device"
        results["geolocation"] = {
            "status": "private",
            "country": payload["country"],
            "city": payload["city"],
            "isp": "Private",
            "org": payload["org"],
            "lat": None,
            "lon": None,
        }
        results["ipinfo"] = {
            "ip": ip_address,
            "hostname": results.get("hostname"),
            "org": payload["org"],
            "country": "Local",
        }
    else:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(
                    f"http://ip-api.com/json/{ip_address}",
                    params={
                        "fields": "status,message,country,regionName,city,isp,org,lat,lon,as,reverse,mobile,proxy,hosting,query"
                    },
                )
                resp.raise_for_status()
                geolocation = resp.json()
        except httpx.TimeoutException as exc:
            logger.warning("IP lookup timed out for %s: %s", ip_address, exc)
            raise HTTPException(status_code=504, detail="Timed out while looking up the IP address") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning("IP lookup HTTP error for %s: %s", ip_address, exc.response.status_code)
            raise HTTPException(status_code=502, detail="IP lookup provider returned an error") from exc
        except httpx.RequestError as exc:
            logger.warning("IP lookup request failed for %s: %s", ip_address, exc)
            raise HTTPException(status_code=502, detail="Unable to reach the IP lookup provider") from exc

        if geolocation.get("status") != "success":
            detail = geolocation.get("message") or "IP lookup failed"
            raise HTTPException(status_code=502, detail=detail)

        results["geolocation"] = geolocation
        results["ipinfo"] = {
            "ip": ip_address,
            "city": geolocation.get("city"),
            "region": geolocation.get("regionName"),
            "country": geolocation.get("country"),
            "org": geolocation.get("org") or geolocation.get("isp"),
        }
        payload["country"] = geolocation.get("country")
        payload["city"] = geolocation.get("city")
        payload["org"] = geolocation.get("org") or geolocation.get("isp")
        payload["lat"] = geolocation.get("lat")
        payload["lon"] = geolocation.get("lon")

    payload["intel"] = results
    payload["checked_at"] = datetime.utcnow().isoformat()
    _latest_live_results["ip_lookup"] = payload
    try:
        db.save_live_tool_result("ip_lookup", payload)
        db.add_event(
            event_id=f"evt_ip_{ip_address}_{uuid.uuid4().hex[:8]}",
            event_type="ip_lookup",
            source="julius-tools",
            data={"ip": ip_address, "result": payload},
        )

        # Auto-create identity for looked up IP
        try:
            import uuid
            existing = db.get_identities()
            handles = [i.get("handle") for i in existing]
            if ip_address not in handles:
                identity_id = f"id-{uuid.uuid4().hex[:6]}"
                conn = db._connect()
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO identities (id, name, platform, handle, email, phone, created_at) VALUES (?,?,?,?,?,?,?)",
                        (identity_id, f"{payload.get('org', 'Unknown')}_{ip_address}", "osint", ip_address, None, None, datetime.utcnow().isoformat()),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            logger.warning(f"Auto identity from IP lookup failed: {e}")
    except Exception:
        pass
    return payload


async def _lookup_dns_payload(domain: str) -> Dict[str, Any]:
    normalized = domain.strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="Domain is required")

    results: Dict[str, Any] = {"resolved": False}
    records: List[Dict[str, str]] = []
    a_records: List[str] = []
    aaaa_records: List[str] = []

    try:
        addrinfo = socket.getaddrinfo(normalized, None)
    except socket.gaierror as exc:
        results["error"] = str(exc)
        return {
            "domain": normalized,
            "records": [],
            "dns": results,
            "checked_at": datetime.utcnow().isoformat(),
        }

    seen = set()
    for family, _, _, _, sockaddr in addrinfo:
        address = sockaddr[0]
        record_type = "A" if family == socket.AF_INET else "AAAA" if family == socket.AF_INET6 else str(family)
        key = (record_type, address)
        if key in seen:
            continue
        seen.add(key)
        records.append({"type": record_type, "address": address})
        if family == socket.AF_INET:
            a_records.append(address)
        elif family == socket.AF_INET6:
            aaaa_records.append(address)

    results["resolved"] = bool(records)
    results["a_records"] = a_records
    results["aaaa_records"] = aaaa_records

    if records:
        try:
            rev = socket.gethostbyaddr(records[0]["address"])
            results["reverse_dns"] = rev[0]
        except Exception:
            results["reverse_dns"] = None

    payload = {
        "domain": normalized,
        "records": records,
        "dns": results,
        "checked_at": datetime.utcnow().isoformat(),
    }
    _latest_live_results["dns_lookup"] = payload
    try:
        db.save_live_tool_result("dns_lookup", payload)
        db.add_event(
            event_id=f"evt_dns_{normalized}_{uuid.uuid4().hex[:8]}",
            event_type="dns_lookup",
            source="julius-tools",
            data={"domain": normalized, "result": payload},
        )
    except Exception:
        pass
    return payload


@router.get("/threats/cve-latest")
async def latest_cves():
    """Fetch latest CVEs from NIST NVD (free, no API key needed)."""
    return await _fetch_latest_cves_payload()


@router.get("/cves")
async def latest_cves_alias():
    """Alias used by the frontend tools panel."""
    return await _fetch_latest_cves_payload()


@router.get("/threats/ip/{ip_address}")
async def lookup_ip_threat(ip_address: str):
    """Check an IP — uses LAN detection for private IPs, public APIs for public IPs."""
    import ipaddress as _ipa
    import subprocess as _sp
    import re as _re

    results = {}
    is_private = False
    try:
        is_private = _ipa.ip_address(ip_address).is_private
    except ValueError:
        pass

    results["network_type"] = "Private LAN" if is_private else "Public Internet"

    if is_private:
        # Ping
        ping_flag = "-n" if platform.system() == "Windows" else "-c"
        try:
            pr = _sp.run(["ping", ping_flag, "2", "-w", "1500", ip_address],
                         capture_output=True, text=True, timeout=8)
            alive = "TTL=" in pr.stdout.upper() or "ttl=" in pr.stdout or "bytes from" in pr.stdout
            results["host_alive"] = alive
            lat = _re.search(r'time[=<](\d+(?:\.\d+)?)\s*ms', pr.stdout)
            results["latency_ms"] = float(lat.group(1)) if lat else None
        except Exception:
            results["host_alive"] = None

        # Hostname
        try:
            results["hostname"] = socket.gethostbyaddr(ip_address)[0]
        except Exception:
            results["hostname"] = None

        # MAC via ARP
        try:
            arp = _sp.run(["arp", "-a", ip_address], capture_output=True, text=True, timeout=5)
            mac = _re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', arp.stdout)
            results["mac_address"] = mac.group(0) if mac else None
        except Exception:
            results["mac_address"] = None

        # MAC vendor lookup
        if results.get("mac_address"):
            prefix = results["mac_address"].replace("-", ":").upper()[:8]
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(f"https://api.macvendors.com/{prefix}")
                    results["device_vendor"] = resp.text if resp.status_code == 200 else None
            except Exception:
                results["device_vendor"] = None

        # Quick port probe
        common = [22, 80, 135, 139, 443, 445, 3389, 8080]
        open_ports = []
        for port in common:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1.0)
                    if s.connect_ex((ip_address, port)) == 0:
                        open_ports.append(port)
            except Exception:
                pass
        results["open_ports"] = open_ports

        results["geolocation"] = {"status": "private", "country": "Local Network", "city": "LAN",
                                   "isp": "Private", "org": results.get("hostname") or "Unknown Device"}
        results["ipinfo"] = {"ip": ip_address, "hostname": results.get("hostname"),
                              "org": results.get("device_vendor") or "LAN Device",
                              "country": "Local"}
    else:
        # Public IP — use external APIs
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"http://ip-api.com/json/{ip_address}?fields=status,message,country,regionName,city,isp,org,as,reverse,mobile,proxy,hosting,query")
                if resp.status_code == 200:
                    results["geolocation"] = resp.json()
        except Exception as e:
            results["geolocation"] = {"error": str(e)}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://ipinfo.io/{ip_address}/json")
                if resp.status_code == 200:
                    results["ipinfo"] = resp.json()
        except Exception as e:
            results["ipinfo"] = {"error": str(e)}

    return {
        "ip": ip_address,
        "intel": results,
        "checked_at": datetime.utcnow().isoformat(),
    }


@router.get("/threats/dns/{domain}")
async def dns_lookup(domain: str):
    """Real DNS resolution for a domain."""
    results = {}
    try:
        ips = socket.getaddrinfo(domain, None)
        unique_ips = list(set(addr[4][0] for addr in ips))
        results["a_records"] = unique_ips
        results["resolved"] = True
    except socket.gaierror as e:
        results["resolved"] = False
        results["error"] = str(e)

    # Reverse DNS for first IP
    if results.get("a_records"):
        try:
            rev = socket.gethostbyaddr(results["a_records"][0])
            results["reverse_dns"] = rev[0]
        except Exception:
            results["reverse_dns"] = None

    return {"domain": domain, "dns": results, "checked_at": datetime.utcnow().isoformat()}


@router.get("/ip/{ip_address}")
async def lookup_ip(ip_address: str):
    """Frontend alias for live IP lookups."""
    return await _lookup_ip_payload(ip_address)


@router.get("/dns/{domain}")
async def dns_lookup_alias(domain: str):
    """Frontend alias for live DNS lookups."""
    return await _lookup_dns_payload(domain)


# ═══════════════════════════════════════════════════════════════════════════
# 4. AUTO-SCAN ON STARTUP
# ═══════════════════════════════════════════════════════════════════════════

_startup_scanned = False


def run_startup_scan():
    """Auto-scan localhost to seed real data into the DB."""
    global _startup_scanned
    if _startup_scanned:
        return
    _startup_scanned = True

    logger.info("Running startup auto-scan of localhost...")
    from .scanner import _check_port, _detect_vulnerabilities, TOP_PORTS

    scan_id = f"scan_startup_{uuid.uuid4().hex[:8]}"
    db.create_scan(scan_id, "127.0.0.1", "auto-startup", "system")

    open_ports = []
    all_results = []
    for port in TOP_PORTS:
        result = _check_port("127.0.0.1", port, 1.0)
        all_results.append(result)
        if result["status"] == "open":
            open_ports.append(result)

    vulns = _detect_vulnerabilities(scan_id, "127.0.0.1", open_ports)

    db.update_scan(scan_id, "completed", {
        "target": "127.0.0.1",
        "total_ports_scanned": len(TOP_PORTS),
        "open_ports": open_ports,
        "vulnerabilities": vulns,
    })

    # Generate events for each open port
    for p in open_ports:
        db.add_event(
            event_id=f"evt_autoport_{p['port']}_{uuid.uuid4().hex[:4]}",
            event_type="port_discovered",
            source="julius-autoscan",
            data={"host": "127.0.0.1", "port": p["port"], "service": p["service"], "banner": p.get("banner", "")}
        )

    # Generate behavioral alerts for suspicious services
    suspicious_services = {"telnet", "ftp", "vnc", "msrpc", "netbios-ssn", "microsoft-ds", "redis", "mongodb"}
    for p in open_ports:
        if p["service"] in suspicious_services:
            db.add_behavioral_alert(
                pattern_id=1,
                alert_type="risky_service",
                severity="high" if p["service"] in ("telnet", "ftp", "redis") else "medium",
                message=f"Potentially risky service '{p['service']}' detected on localhost port {p['port']}",
                data={"host": "127.0.0.1", "port": p["port"], "service": p["service"]}
            )

    # Scan local network gateway if possible
    try:
        gw = _get_default_gateway()
        if gw and gw != "127.0.0.1":
            gw_scan_id = f"scan_gateway_{uuid.uuid4().hex[:8]}"
            db.create_scan(gw_scan_id, gw, "auto-gateway", "system")
            gw_open = []
            for port in TOP_PORTS[:15]:
                r = _check_port(gw, port, 1.5)
                if r["status"] == "open":
                    gw_open.append(r)
            gw_vulns = _detect_vulnerabilities(gw_scan_id, gw, gw_open)
            db.update_scan(gw_scan_id, "completed", {
                "target": gw, "total_ports_scanned": 15,
                "open_ports": gw_open, "vulnerabilities": gw_vulns,
            })
            for p in gw_open:
                db.add_event(
                    event_id=f"evt_gwport_{p['port']}_{uuid.uuid4().hex[:4]}",
                    event_type="gateway_port_discovered",
                    source="julius-autoscan",
                    data={"host": gw, "port": p["port"], "service": p["service"]}
                )
            logger.info(f"Gateway scan ({gw}): {len(gw_open)} open ports, {len(gw_vulns)} vulns")
    except Exception as e:
        logger.warning(f"Gateway scan skipped: {e}")

    # Seed events from real network connections
    try:
        conns = psutil.net_connections(kind="inet")
        external = set()
        for c in conns:
            if c.raddr and c.status == "ESTABLISHED":
                remote_ip = c.raddr.ip
                if not remote_ip.startswith("127.") and not remote_ip.startswith("0."):
                    external.add(remote_ip)
        for ip in list(external)[:10]:
            db.add_event(
                event_id=f"evt_extconn_{ip.replace('.','_')}_{uuid.uuid4().hex[:4]}",
                event_type="external_connection",
                source="julius-netmon",
                data={"remote_ip": ip, "status": "ESTABLISHED"}
            )
    except Exception as e:
        logger.warning(f"Connection scan skipped: {e}")

    db.add_event(
        event_id=f"evt_autoscan_done_{uuid.uuid4().hex[:6]}",
        event_type="startup_scan_complete",
        source="julius-system",
        data={"localhost_ports": len(open_ports), "localhost_vulns": len(vulns)}
    )
    logger.info(f"Startup scan complete: {len(open_ports)} open ports, {len(vulns)} vulns")


async def run_startup_live_tools():
    """Run baseline live tool lookups on startup."""
    try:
        logger.info("Running startup live tools baseline lookups...")
        await _lookup_ip_payload("8.8.8.8")
        await _lookup_dns_payload("google.com")
        await _fetch_latest_cves_payload()
        logger.info("Startup live tools baseline complete")
    except Exception as exc:
        logger.warning("Startup live tools baseline failed: %s", exc)


def _get_default_gateway():
    """Get default gateway IP (cross-platform)."""
    import subprocess
    system = platform.system()
    try:
        if system == "Windows":
            result = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split("\n"):
                if "Default Gateway" in line and ":" in line:
                    parts = line.split(":")
                    if len(parts) > 1:
                        gw = parts[-1].strip()
                        if gw and "." in gw:
                            return gw
        elif system == "Linux":
            result = subprocess.run(
                ["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if line.startswith("default via "):
                    parts = line.split()
                    if len(parts) >= 3:
                        return parts[2]
        elif system == "Darwin":
            result = subprocess.run(
                ["route", "-n", "get", "default"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "gateway:" in line:
                    gw = line.split("gateway:")[-1].strip()
                    if gw and "." in gw:
                        return gw
    except Exception:
        pass
    return None


@router.post("/autoscan")
async def trigger_autoscan(background_tasks: BackgroundTasks):
    """Manually trigger the auto-scan."""
    global _startup_scanned
    _startup_scanned = False
    background_tasks.add_task(run_startup_scan)
    return {"status": "started", "message": "Auto-scan running in background"}


# ═══════════════════════════════════════════════════════════════════════════
# 5. LIVE DASHBOARD AGGREGATION
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/dashboard")
async def live_dashboard():
    """All real data for the dashboard in one call."""
    mem = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=0.3)
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    conns = psutil.net_connections(kind="inet")

    established = sum(1 for c in conns if c.status == "ESTABLISHED")
    listening = sum(1 for c in conns if c.status == "LISTEN")

    stats = db.get_system_stats()
    recent_events = db.get_recent_events(15)
    recent_scans = db.get_recent_scans(5)
    alerts = db.get_behavioral_alerts(10)
    vulns = db.get_vulnerabilities(limit=10)

    return {
        "system": {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "disk_percent": round(disk.percent, 1),
            "net_mb_sent": round(net.bytes_sent / (1024**2), 1),
            "net_mb_recv": round(net.bytes_recv / (1024**2), 1),
            "connections_established": established,
            "connections_listening": listening,
            "hostname": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
        },
        "stats": stats,
        "recent_events": recent_events,
        "recent_scans": recent_scans,
        "recent_alerts": alerts,
        "recent_vulns": vulns,
        "timestamp": datetime.utcnow().isoformat(),
    }
