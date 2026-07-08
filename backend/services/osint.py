"""
JULIUS OSINT Service — Aggregated open-source intelligence from multiple providers.
"""

import os
import logging
import httpx

logger = logging.getLogger(__name__)


async def whois_lookup(domain: str) -> dict:
    """WHOIS lookup via public API."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://api.api-ninjas.com/v1/whois?domain={domain}",
                                     headers={"X-Api-Key": os.getenv("API_NINJAS_KEY", "")})
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    try:
        import whois
        w = whois.whois(domain)
        return {"domain": domain, "registrar": w.registrar, "creation_date": str(w.creation_date),
                "expiration_date": str(w.expiration_date), "name_servers": w.name_servers}
    except ImportError:
        return {"domain": domain, "error": "python-whois not installed and no API key configured"}
    except Exception as e:
        return {"domain": domain, "error": str(e)}


async def shodan_lookup(ip: str) -> dict:
    """Shodan host lookup (requires SHODAN_API_KEY)."""
    api_key = os.getenv("SHODAN_API_KEY", "")
    if not api_key:
        return {"ip": ip, "error": "SHODAN_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://api.shodan.io/shodan/host/{ip}?key={api_key}")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ip": ip, "hostnames": data.get("hostnames", []),
                    "ports": data.get("ports", []), "os": data.get("os"),
                    "org": data.get("org"), "isp": data.get("isp"),
                    "country": data.get("country_name"),
                    "vulns": data.get("vulns", []),
                }
            return {"ip": ip, "error": f"Shodan returned {resp.status_code}"}
    except Exception as e:
        return {"ip": ip, "error": str(e)}


async def virustotal_check(ioc: str) -> dict:
    """VirusTotal IOC check (requires VT_API_KEY)."""
    api_key = os.getenv("VT_API_KEY", "")
    if not api_key:
        return {"ioc": ioc, "error": "VT_API_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"https://www.virustotal.com/api/v3/search?query={ioc}",
                                     headers={"x-apikey": api_key})
            if resp.status_code == 200:
                return resp.json()
            return {"ioc": ioc, "error": f"VT returned {resp.status_code}"}
    except Exception as e:
        return {"ioc": ioc, "error": str(e)}


async def abuseipdb_check(ip: str) -> dict:
    """AbuseIPDB check (requires ABUSEIPDB_KEY)."""
    api_key = os.getenv("ABUSEIPDB_KEY", "")
    if not api_key:
        return {"ip": ip, "error": "ABUSEIPDB_KEY not configured"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://api.abuseipdb.com/api/v2/check",
                                     params={"ipAddress": ip, "maxAgeInDays": 90},
                                     headers={"Key": api_key, "Accept": "application/json"})
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return {
                    "ip": ip, "abuse_confidence": data.get("abuseConfidenceScore"),
                    "country": data.get("countryCode"), "isp": data.get("isp"),
                    "domain": data.get("domain"), "total_reports": data.get("totalReports"),
                    "is_public": data.get("isPublic"),
                }
            return {"ip": ip, "error": f"AbuseIPDB returned {resp.status_code}"}
    except Exception as e:
        return {"ip": ip, "error": str(e)}
