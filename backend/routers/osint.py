"""
JULIUS OSINT Router — Open-source intelligence endpoints.
AXIOM + Causal Functor pipeline runs automatically after enrichment lookups.
"""
import asyncio
import httpx
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..services.export_pipeline import build_job_export
from ..services.osint import whois_lookup, shodan_lookup, virustotal_check, abuseipdb_check
from ..services.uk_signal_collector import (
    DEFAULT_GITHUB_ENRICHMENTS,
    DEFAULT_GITHUB_PAGES,
    DEFAULT_GDELT_RESULTS_PER_QUERY,
    DEFAULT_DOC_ALIGNED_QUERIES,
    DEFAULT_GITLAB_RESULTS_PER_QUERY,
    DEFAULT_GOVUK_RESULTS_PER_QUERY,
    DEFAULT_HOSTSEARCH_RESULTS_PER_ZONE,
    DEFAULT_HOSTSEARCH_ZONES,
    DEFAULT_IPINFO_LOOKUPS,
    DEFAULT_NPM_RESULTS_PER_QUERY,
    DEFAULT_OSM_QUERIES,
    DEFAULT_OSM_RESULTS_PER_QUERY,
    DEFAULT_PUBLIC_SPENDING_QUERIES,
    DEFAULT_PUBLIC_SOURCE_QUERIES,
    DEFAULT_PYPI_PACKAGE_LIMIT,
    DEFAULT_SPENDING_RESULTS_PER_QUERY,
    DEFAULT_TARGET_PROFILES,
    collector,
)

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/osint", tags=["OSINT"])


# ── AXIOM enrichment helper ───────────────────────────────────────────────

async def _run_osint_pipeline(
    target: str,
    osint_data: dict,
    source: str = "osint",
) -> dict:
    """
    Run AXIOM + causal functor pipeline on OSINT results.
    Returns enriched analysis. Non-fatal — errors are logged, not raised.
    """
    try:
        from ..integration.pipeline import run_intelligence_pipeline
        result = await run_intelligence_pipeline(
            scan_results=[],          # no port scan data for OSINT lookups
            osint_data=osint_data,
            target=target,
            depth="standard",
        )
        logger.info("AXIOM OSINT pipeline completed for %s (%s)", target, source)
        return result
    except Exception as e:
        logger.warning("AXIOM OSINT pipeline skipped for %s: %s", target, e)
        return {}


# ── Request Models ────────────────────────────────────────────────────────

class UKCollectionRequest(BaseModel):
    target_profiles: int = Field(default=DEFAULT_TARGET_PROFILES, ge=1, le=250000)
    github_queries: list[str] | None = None
    allowlisted_domains: list[str] = Field(default_factory=list)
    hostsearch_zones: list[str] = Field(default_factory=lambda: list(DEFAULT_HOSTSEARCH_ZONES))
    gitlab_queries: list[str] = Field(default_factory=list)
    npm_queries: list[str] = Field(default_factory=list)
    pypi_packages: list[str] = Field(default_factory=list)
    govuk_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_PUBLIC_SOURCE_QUERIES))
    spending_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_PUBLIC_SPENDING_QUERIES))
    gdelt_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_DOC_ALIGNED_QUERIES))
    osm_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_OSM_QUERIES))
    max_github_pages: int = Field(default=DEFAULT_GITHUB_PAGES, ge=1, le=10)
    max_github_enrichments: int = Field(default=DEFAULT_GITHUB_ENRICHMENTS, ge=0, le=250)
    max_hostsearch_results_per_zone: int = Field(default=DEFAULT_HOSTSEARCH_RESULTS_PER_ZONE, ge=1, le=100)
    max_ipinfo_lookups: int = Field(default=DEFAULT_IPINFO_LOOKUPS, ge=0, le=200)
    max_gitlab_results_per_query: int = Field(default=DEFAULT_GITLAB_RESULTS_PER_QUERY, ge=1, le=100)
    max_npm_results_per_query: int = Field(default=DEFAULT_NPM_RESULTS_PER_QUERY, ge=1, le=100)
    max_pypi_package_lookups: int = Field(default=DEFAULT_PYPI_PACKAGE_LIMIT, ge=0, le=100)
    max_govuk_results_per_query: int = Field(default=DEFAULT_GOVUK_RESULTS_PER_QUERY, ge=1, le=100)
    max_spending_results_per_query: int = Field(default=DEFAULT_SPENDING_RESULTS_PER_QUERY, ge=1, le=100)
    max_gdelt_results_per_query: int = Field(default=DEFAULT_GDELT_RESULTS_PER_QUERY, ge=1, le=100)
    max_osm_results_per_query: int = Field(default=DEFAULT_OSM_RESULTS_PER_QUERY, ge=1, le=50)


# ── OSINT Lookup Endpoints (now with AXIOM enrichment) ───────────────────

@router.get("/whois/{domain}")
async def whois(domain: str):
    """WHOIS lookup + AXIOM intelligence analysis."""
    result = await whois_lookup(domain)

    # Build OSINT payload for pipeline
    osint_data = {
        "domains": [domain],
        "emails": _extract_list(result, "emails"),
        "phones": _extract_list(result, "phones"),
        "ips":    _extract_list(result, "ips"),
        "usernames": [],
    }
    axiom = await _run_osint_pipeline(domain, osint_data, source="whois")
    if axiom:
        result["axiom_analysis"] = axiom.get("summary")
        result["axiom_findings"] = axiom.get("axiom_findings", [])

    return result


@router.get("/shodan/{ip}")
async def shodan(ip: str):
    """Shodan lookup + AXIOM intelligence analysis."""
    result = await shodan_lookup(ip)

    ports    = result.get("ports", [])
    services = result.get("services", {})
    vulns    = result.get("vulns", [])

    # Feed into pipeline as a scan result
    from ..integration.pipeline import run_intelligence_pipeline
    try:
        scan_payload = [{
            "target": ip,
            "ports": ports if isinstance(ports, list) else [],
            "vulnerabilities": vulns if isinstance(vulns, list) else [],
            "services": services if isinstance(services, dict) else {},
            "risk_score": float(result.get("risk_score", 0)),
            "open_ports_count": len(ports),
        }]
        axiom = await run_intelligence_pipeline(
            scan_results=scan_payload,
            osint_data={"ips": [ip], "domains": [], "emails": [], "phones": [], "usernames": []},
            target=ip,
            depth="standard",
        )
        result["axiom_analysis"] = axiom.get("summary")
        result["axiom_findings"] = axiom.get("axiom_findings", [])
    except Exception as e:
        logger.warning("Shodan AXIOM pipeline skipped: %s", e)

    return result


@router.get("/virustotal/{ioc}")
async def virustotal(ioc: str):
    """VirusTotal IOC check + AXIOM intelligence analysis."""
    result = await virustotal_check(ioc)

    osint_data = {
        "domains": [ioc] if "." in ioc and not ioc.replace(".", "").isdigit() else [],
        "ips":     [ioc] if ioc.replace(".", "").isdigit() else [],
        "emails":  [], "phones": [], "usernames": [],
    }
    axiom = await _run_osint_pipeline(ioc, osint_data, source="virustotal")
    if axiom:
        result["axiom_analysis"] = axiom.get("summary")

    return result


@router.get("/abuseipdb/{ip}")
async def abuseipdb(ip: str):
    """AbuseIPDB check + AXIOM intelligence analysis."""
    result = await abuseipdb_check(ip)

    osint_data = {
        "ips": [ip],
        "domains": [], "emails": [], "phones": [], "usernames": [],
    }
    axiom = await _run_osint_pipeline(ip, osint_data, source="abuseipdb")
    if axiom:
        result["axiom_analysis"] = axiom.get("summary")

    return result


# ── UK Collection ─────────────────────────────────────────────────────────

@router.post("/collect/uk")
async def collect_uk_signals(req: UKCollectionRequest):
    job = await collector.start_collection(
        target_profiles=req.target_profiles,
        github_queries=req.github_queries,
        allowlisted_domains=req.allowlisted_domains,
        hostsearch_zones=req.hostsearch_zones,
        gitlab_queries=req.gitlab_queries,
        npm_queries=req.npm_queries,
        pypi_packages=req.pypi_packages,
        govuk_queries=req.govuk_queries,
        spending_queries=req.spending_queries,
        gdelt_queries=req.gdelt_queries,
        osm_queries=req.osm_queries,
        max_github_pages=req.max_github_pages,
        max_github_enrichments=req.max_github_enrichments,
        max_hostsearch_results_per_zone=req.max_hostsearch_results_per_zone,
        max_ipinfo_lookups=req.max_ipinfo_lookups,
        max_gitlab_results_per_query=req.max_gitlab_results_per_query,
        max_npm_results_per_query=req.max_npm_results_per_query,
        max_pypi_package_lookups=req.max_pypi_package_lookups,
        max_govuk_results_per_query=req.max_govuk_results_per_query,
        max_spending_results_per_query=req.max_spending_results_per_query,
        max_gdelt_results_per_query=req.max_gdelt_results_per_query,
        max_osm_results_per_query=req.max_osm_results_per_query,
    )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "mode": "public_profile_safe",
        "constraints": job.constraints,
        "status_url": f"/api/osint/collect/status/{job.job_id}",
    }


@router.post("/collect/uk/stop/{job_id}")
async def stop_uk_collection(job_id: str):
    job = await collector.stop_collection(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Collection job not found")
    return collector.serialize_job(job)


@router.get("/collect/status/{job_id}")
async def uk_collection_status(job_id: str):
    job = collector.get_job_snapshot(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Collection job not found")
    return job


@router.get("/collect/export/{job_id}")
async def export_uk_collection(job_id: str) -> dict[str, Any]:
    snapshot = collector.get_job_snapshot(job_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Collection job not found")
    raw = collector.export_job_profiles(job_id)
    profiles = raw.get("profiles") or []
    if not profiles:
        raise HTTPException(
            status_code=404,
            detail=f"No profiles collected yet for job {job_id}.",
        )
    return build_job_export(
        profiles,
        job_id=job_id,
        input_profile_count=int(raw.get("count") or len(profiles)),
    )


# ── Threat Feed Sources ───────────────────────────────────────────────────

FEODO_URL           = "https://feodotracker.abuse.ch/downloads/ipblocklist_aggressive.json"
CINSSCORE_URL       = "https://cinsscore.com/list/ci-badguys.txt"
EMERGINGTHREATS_URL = "https://rules.emergingthreats.net/blockrules/compromised-ips.txt"


async def _fetch_feodo() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(FEODO_URL)
            r.raise_for_status()
            data = r.json()
            results = []
            for entry in data[:80]:
                ip = entry.get("ip_address", "")
                if not ip:
                    continue
                malware     = entry.get("malware", "Unknown")
                status      = entry.get("status", "offline")
                last_online = entry.get("last_online", "")
                country     = entry.get("country", "??")
                results.append({
                    "id": f"feodo-{ip.replace('.', '-')}",
                    "ip": ip,
                    "source": "Feodo Tracker (abuse.ch)",
                    "risk_level": "Critical" if status == "online" else "High",
                    "tags": ["botnet", "c2", malware.lower().replace(" ", "-")],
                    "country": country,
                    "last_seen": last_online + "T00:00:00Z" if last_online and "T" not in last_online else (last_online or ""),
                    "first_seen": entry.get("first_seen", ""),
                    "details": f"{malware} C2 server [{status.upper()}]",
                })
            return results
    except Exception:
        return []


async def _fetch_emergingthreats() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(EMERGINGTHREATS_URL)
            r.raise_for_status()
            lines = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            return [
                {
                    "id": f"et-{ip.replace('.', '-')}",
                    "ip": ip,
                    "source": "Emerging Threats",
                    "risk_level": "High",
                    "tags": ["compromised", "scanner", "attacker"],
                    "country": "",
                    "last_seen": now,
                    "first_seen": "",
                    "details": "Confirmed compromised host — active attacker",
                }
                for ip in lines[:60]
            ]
    except Exception:
        return []


async def _fetch_cinsscore() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(CINSSCORE_URL)
            r.raise_for_status()
            lines = [l.strip() for l in r.text.splitlines()
                     if l.strip() and not l.startswith(";") and not l.startswith("#")]
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            return [
                {
                    "id": f"cins-{ip.replace('.', '-')}",
                    "ip": ip,
                    "source": "CINS Score",
                    "risk_level": "Medium",
                    "tags": ["bad-actor", "threat-intel", "cins"],
                    "country": "",
                    "last_seen": now,
                    "first_seen": "",
                    "details": "Listed in CINS Score bad actors list",
                }
                for ip in lines[:60]
            ]
    except Exception:
        return []


@router.get("/feeds")
async def feeds():
    return await threat_feeds()


@router.get("/threat-feeds")
async def threat_feeds():
    """
    Real-time aggregated threat intelligence from public free feeds.
    AXIOM anomaly scoring applied to the aggregated results.
    """
    feodo, et, cins = await asyncio.gather(
        _fetch_feodo(),
        _fetch_emergingthreats(),
        _fetch_cinsscore(),
    )
    all_feeds = feodo + et + cins

    # Deduplicate by IP
    seen, unique_feeds = set(), []
    for f in all_feeds:
        if f["ip"] not in seen:
            seen.add(f["ip"])
            unique_feeds.append(f)

    risk_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    unique_feeds.sort(key=lambda x: (risk_order.get(x["risk_level"], 9), -(len(x["last_seen"]))))

    # Run AXIOM pipeline on the aggregated feed (sample: top 10 IPs)
    axiom_summary = None
    try:
        sample_ips = [f["ip"] for f in unique_feeds[:10]]
        if sample_ips:
            from ..integration.pipeline import run_intelligence_pipeline
            pipeline = await run_intelligence_pipeline(
                scan_results=[],
                osint_data={
                    "ips": sample_ips,
                    "domains": [], "emails": [], "phones": [], "usernames": [],
                },
                target="threat_feed_aggregate",
                depth="standard",
            )
            axiom_summary = pipeline.get("summary")
    except Exception as e:
        logger.warning("Threat feed AXIOM pipeline skipped: %s", e)

    return {
        "status": "success",
        "count": len(unique_feeds),
        "sources": {
            "feodo_tracker":    len(feodo),
            "emerging_threats": len(et),
            "cins_score":       len(cins),
        },
        "axiom_analysis": axiom_summary,
        "data": unique_feeds,
    }


@router.get("/globe-events")
async def globe_events():
    """Threat events for globe visualization."""
    from datetime import datetime, timezone
    try:
        feodo, et, cins = await asyncio.gather(
            _fetch_feodo(),
            _fetch_emergingthreats(),
            _fetch_cinsscore(),
            return_exceptions=True,
        )
        feodo = feodo if isinstance(feodo, list) else []
        et    = et    if isinstance(et,    list) else []
        cins  = cins  if isinstance(cins,  list) else []

        events = [
            {
                "id":         f.get("id"),
                "ip":         f.get("ip"),
                "source":     f.get("source"),
                "risk_level": f.get("risk_level"),
                "country":    f.get("country"),
                "timestamp":  f.get("last_seen", datetime.now(timezone.utc).isoformat()),
                "tags":       f.get("tags", []),
                "details":    f.get("details"),
            }
            for f in (feodo + et + cins)
        ]
        return {
            "status": "ok",
            "events": events,
            "count": len(events),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "ok",
            "events": [],
            "count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


# ── Helpers ───────────────────────────────────────────────────────────────

def _extract_list(data: dict, key: str) -> list:
    """Safely extract a list from a result dict."""
    val = data.get(key, [])
    return val if isinstance(val, list) else []







# """
# JULIUS OSINT Router — Open-source intelligence endpoints.
# """

# import asyncio
# import httpx
# from typing import Any

# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel, Field

# from ..services.export_pipeline import build_job_export
# from ..services.osint import whois_lookup, shodan_lookup, virustotal_check, abuseipdb_check
# from ..services.uk_signal_collector import (
#     DEFAULT_GITHUB_ENRICHMENTS,
#     DEFAULT_GITHUB_PAGES,
#     DEFAULT_GDELT_RESULTS_PER_QUERY,
#     DEFAULT_DOC_ALIGNED_QUERIES,
#     DEFAULT_GITLAB_RESULTS_PER_QUERY,
#     DEFAULT_GOVUK_RESULTS_PER_QUERY,
#     DEFAULT_HOSTSEARCH_RESULTS_PER_ZONE,
#     DEFAULT_HOSTSEARCH_ZONES,
#     DEFAULT_IPINFO_LOOKUPS,
#     DEFAULT_NPM_RESULTS_PER_QUERY,
#     DEFAULT_OSM_QUERIES,
#     DEFAULT_OSM_RESULTS_PER_QUERY,
#     DEFAULT_PUBLIC_SPENDING_QUERIES,
#     DEFAULT_PUBLIC_SOURCE_QUERIES,
#     DEFAULT_PYPI_PACKAGE_LIMIT,
#     DEFAULT_SPENDING_RESULTS_PER_QUERY,
#     DEFAULT_TARGET_PROFILES,
#     collector,
# )

# router = APIRouter(prefix="/api/osint", tags=["OSINT"])


# class UKCollectionRequest(BaseModel):
#     target_profiles: int = Field(default=DEFAULT_TARGET_PROFILES, ge=1, le=250000)
#     github_queries: list[str] | None = None
#     allowlisted_domains: list[str] = Field(default_factory=list)
#     hostsearch_zones: list[str] = Field(default_factory=lambda: list(DEFAULT_HOSTSEARCH_ZONES))
#     gitlab_queries: list[str] = Field(default_factory=list)
#     npm_queries: list[str] = Field(default_factory=list)
#     pypi_packages: list[str] = Field(default_factory=list)
#     govuk_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_PUBLIC_SOURCE_QUERIES))
#     spending_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_PUBLIC_SPENDING_QUERIES))
#     gdelt_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_DOC_ALIGNED_QUERIES))
#     osm_queries: list[str] = Field(default_factory=lambda: list(DEFAULT_OSM_QUERIES))
#     max_github_pages: int = Field(default=DEFAULT_GITHUB_PAGES, ge=1, le=10)
#     max_github_enrichments: int = Field(default=DEFAULT_GITHUB_ENRICHMENTS, ge=0, le=250)
#     max_hostsearch_results_per_zone: int = Field(default=DEFAULT_HOSTSEARCH_RESULTS_PER_ZONE, ge=1, le=100)
#     max_ipinfo_lookups: int = Field(default=DEFAULT_IPINFO_LOOKUPS, ge=0, le=200)
#     max_gitlab_results_per_query: int = Field(default=DEFAULT_GITLAB_RESULTS_PER_QUERY, ge=1, le=100)
#     max_npm_results_per_query: int = Field(default=DEFAULT_NPM_RESULTS_PER_QUERY, ge=1, le=100)
#     max_pypi_package_lookups: int = Field(default=DEFAULT_PYPI_PACKAGE_LIMIT, ge=0, le=100)
#     max_govuk_results_per_query: int = Field(default=DEFAULT_GOVUK_RESULTS_PER_QUERY, ge=1, le=100)
#     max_spending_results_per_query: int = Field(default=DEFAULT_SPENDING_RESULTS_PER_QUERY, ge=1, le=100)
#     max_gdelt_results_per_query: int = Field(default=DEFAULT_GDELT_RESULTS_PER_QUERY, ge=1, le=100)
#     max_osm_results_per_query: int = Field(default=DEFAULT_OSM_RESULTS_PER_QUERY, ge=1, le=50)


# @router.get("/whois/{domain}")
# async def whois(domain: str):
#     return await whois_lookup(domain)


# @router.get("/shodan/{ip}")
# async def shodan(ip: str):
#     return await shodan_lookup(ip)


# @router.get("/virustotal/{ioc}")
# async def virustotal(ioc: str):
#     return await virustotal_check(ioc)


# @router.get("/abuseipdb/{ip}")
# async def abuseipdb(ip: str):
#     return await abuseipdb_check(ip)


# @router.post("/collect/uk")
# async def collect_uk_signals(req: UKCollectionRequest):
#     """
#     Start a safe UK public-profile collection job in the background.
#     """
#     job = await collector.start_collection(
#         target_profiles=req.target_profiles,
#         github_queries=req.github_queries,
#         allowlisted_domains=req.allowlisted_domains,
#         hostsearch_zones=req.hostsearch_zones,
#         gitlab_queries=req.gitlab_queries,
#         npm_queries=req.npm_queries,
#         pypi_packages=req.pypi_packages,
#         govuk_queries=req.govuk_queries,
#         spending_queries=req.spending_queries,
#         gdelt_queries=req.gdelt_queries,
#         osm_queries=req.osm_queries,
#         max_github_pages=req.max_github_pages,
#         max_github_enrichments=req.max_github_enrichments,
#         max_hostsearch_results_per_zone=req.max_hostsearch_results_per_zone,
#         max_ipinfo_lookups=req.max_ipinfo_lookups,
#         max_gitlab_results_per_query=req.max_gitlab_results_per_query,
#         max_npm_results_per_query=req.max_npm_results_per_query,
#         max_pypi_package_lookups=req.max_pypi_package_lookups,
#         max_govuk_results_per_query=req.max_govuk_results_per_query,
#         max_spending_results_per_query=req.max_spending_results_per_query,
#         max_gdelt_results_per_query=req.max_gdelt_results_per_query,
#         max_osm_results_per_query=req.max_osm_results_per_query,
#     )
#     return {
#         "job_id": job.job_id,
#         "status": job.status,
#         "mode": "public_profile_safe",
#         "constraints": job.constraints,
#         "status_url": f"/api/osint/collect/status/{job.job_id}",
#     }


# @router.post("/collect/uk/stop/{job_id}")
# async def stop_uk_collection(job_id: str):
#     job = await collector.stop_collection(job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Collection job not found")
#     return collector.serialize_job(job)


# @router.get("/collect/status/{job_id}")
# async def uk_collection_status(job_id: str):
#     job = collector.get_job_snapshot(job_id)
#     if not job:
#         raise HTTPException(status_code=404, detail="Collection job not found")
#     return job


# @router.get("/collect/export/{job_id}")
# async def export_uk_collection(job_id: str) -> dict[str, Any]:
#     snapshot = collector.get_job_snapshot(job_id)
#     if not snapshot:
#         raise HTTPException(status_code=404, detail="Collection job not found")
#     raw = collector.export_job_profiles(job_id)
#     profiles = raw.get("profiles") or []
#     if not profiles:
#         raise HTTPException(
#             status_code=404,
#             detail=f"No profiles collected yet for job {job_id}. Wait for collection to finish or start a new job.",
#         )
#     return build_job_export(profiles, job_id=job_id, input_profile_count=int(raw.get("count") or len(profiles)))


# # ── Real-time threat feed sources (all free / no API key needed) ──────────────

# FEODO_URL = "https://feodotracker.abuse.ch/downloads/ipblocklist_aggressive.json"
# CINSSCORE_URL = "https://cinsscore.com/list/ci-badguys.txt"
# EMERGINGTHREATS_URL = "https://rules.emergingthreats.net/blockrules/compromised-ips.txt"

# async def _fetch_feodo() -> list[dict]:
#     """Fetch Feodo Tracker botnet C2 IP list (JSON, free, no auth)."""
#     try:
#         async with httpx.AsyncClient(timeout=10) as client:
#             r = await client.get(FEODO_URL)
#             r.raise_for_status()
#             data = r.json()
#             results = []
#             for entry in data[:80]:
#                 ip = entry.get("ip_address", "")
#                 if not ip:
#                     continue
#                 malware = entry.get("malware", "Unknown")
#                 status = entry.get("status", "offline")
#                 last_online = entry.get("last_online", "")
#                 country = entry.get("country", "??")
#                 results.append({
#                     "id": f"feodo-{ip.replace('.', '-')}",
#                     "ip": ip,
#                     "source": "Feodo Tracker (abuse.ch)",
#                     "risk_level": "Critical" if status == "online" else "High",
#                     "tags": ["botnet", "c2", malware.lower().replace(" ", "-")],
#                     "country": country,
#                     "last_seen": last_online + "T00:00:00Z" if last_online and "T" not in last_online else (last_online or ""),
#                     "first_seen": entry.get("first_seen", ""),
#                     "details": f"{malware} C2 server [{status.upper()}]"
#                 })
#             return results
#     except Exception as e:
#         return []


# async def _fetch_emergingthreats() -> list[dict]:
#     """Fetch Emerging Threats compromised IPs (plain text, free, no auth)."""
#     try:
#         async with httpx.AsyncClient(timeout=10) as client:
#             r = await client.get(EMERGINGTHREATS_URL)
#             r.raise_for_status()
#             lines = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith("#")]
#             from datetime import datetime, timezone
#             now = datetime.now(timezone.utc).isoformat()
#             results = []
#             for ip in lines[:60]:
#                 results.append({
#                     "id": f"et-{ip.replace('.', '-')}",
#                     "ip": ip,
#                     "source": "Emerging Threats",
#                     "risk_level": "High",
#                     "tags": ["compromised", "scanner", "attacker"],
#                     "country": "",
#                     "last_seen": now,
#                     "first_seen": "",
#                     "details": "Confirmed compromised host — active attacker"
#                 })
#             return results
#     except Exception:
#         return []


# async def _fetch_cinsscore() -> list[dict]:
#     """Fetch CINS Score CI Bad Guys list (plain text, free, no auth)."""
#     try:
#         async with httpx.AsyncClient(timeout=10) as client:
#             r = await client.get(CINSSCORE_URL)
#             r.raise_for_status()
#             lines = [l.strip() for l in r.text.splitlines() if l.strip() and not l.startswith(";") and not l.startswith("#")]
#             from datetime import datetime, timezone
#             now = datetime.now(timezone.utc).isoformat()
#             results = []
#             for ip in lines[:60]:
#                 results.append({
#                     "id": f"cins-{ip.replace('.', '-')}",
#                     "ip": ip,
#                     "source": "CINS Score",
#                     "risk_level": "Medium",
#                     "tags": ["bad-actor", "threat-intel", "cins"],
#                     "country": "",
#                     "last_seen": now,
#                     "first_seen": "",
#                     "details": "Listed in CINS Score bad actors list"
#                 })
#             return results
#     except Exception:
#         return []


# @router.get("/feeds")
# async def feeds():
#     """
#     OSINT threat feed summary endpoint used by the frontend.
#     Returns the same aggregated threat feed data as /api/osint/threat-feeds.
#     """
#     return await threat_feeds()


# @router.get("/threat-feeds")
# async def threat_feeds():
#     """
#     Real-time aggregated threat intelligence from public free feeds:
#     - Feodo Tracker (abuse.ch) — live botnet C2 servers
#     - Emerging Threats — compromised IPs actively attacking
#     - CINS Score — CI bad guys / known threat actors
#     No API keys required. Data is fresh on every request.
#     """
#     feodo, et, cins = await asyncio.gather(
#         _fetch_feodo(),
#         _fetch_emergingthreats(),
#         _fetch_cinsscore(),
#     )

#     all_feeds = feodo + et + cins

#     # Deduplicate by IP
#     seen = set()
#     unique_feeds = []
#     for f in all_feeds:
#         if f["ip"] not in seen:
#             seen.add(f["ip"])
#             unique_feeds.append(f)

#     # Sort: Critical first, then by last_seen descending
#     risk_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
#     unique_feeds.sort(key=lambda x: (risk_order.get(x["risk_level"], 9), -(len(x["last_seen"]))))

#     return {
#         "status": "success",
#         "count": len(unique_feeds),
#         "sources": {
#             "feodo_tracker": len(feodo),
#             "emerging_threats": len(et),
#             "cins_score": len(cins),
#         },
#         "data": unique_feeds
#     }


# @router.get("/globe-events")
# async def globe_events():
#     """
#     Fetch recent global cyber events and threat activity from aggregated sources.
#     Returns real-time threat event data for the globe visualization.
#     """
#     from datetime import datetime, timezone, timedelta
    
#     try:
#         # Fetch from threat feeds
#         feodo, et, cins = await asyncio.gather(
#             _fetch_feodo(),
#             _fetch_emergingthreats(),
#             _fetch_cinsscore(),
#             return_exceptions=True
#         )
        
#         # Handle exceptions from gather
#         feodo = feodo if isinstance(feodo, list) else []
#         et = et if isinstance(et, list) else []
#         cins = cins if isinstance(cins, list) else []
        
#         all_events = feodo + et + cins
        
#         # Convert to event format for globe visualization
#         events = []
#         for feed in all_events:
#             events.append({
#                 "id": feed.get("id"),
#                 "ip": feed.get("ip"),
#                 "source": feed.get("source"),
#                 "risk_level": feed.get("risk_level"),
#                 "country": feed.get("country"),
#                 "timestamp": feed.get("last_seen", datetime.now(timezone.utc).isoformat()),
#                 "tags": feed.get("tags", []),
#                 "details": feed.get("details")
#             })
        
#         return {
#             "status": "ok",
#             "events": events,
#             "count": len(events),
#             "timestamp": datetime.now(timezone.utc).isoformat()
#         }
#     except Exception as e:
#         return {
#             "status": "ok",
#             "events": [],
#             "count": 0,
#             "timestamp": datetime.now(timezone.utc).isoformat(),
#             "error": str(e)
#         }
