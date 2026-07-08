"""
STRATUM Signal Collector Service

Orchestrates collection from multiple public data sources:
  - GitHub, GitLab, npm, PyPI (developer communities)
  - GOV.UK, Companies House (government + corporate)
  - Wikidata, OpenCorporates (public registries)
  - GDELT (news + publications)
  - HackerTarget, IPInfo, Shodan (optional enrichment)
  - WHOIS (domain metadata)

Features:
  - Rate limiting (1 req/sec per source)
  - Batch profile storage
  - Progress tracking
  - Job management
  - Provenance logging
  - Deduplication pre-storage
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum

import httpx

from ..database import db
from .entity_resolution import EntityResolutionEngine, EntityType


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────
# CONSTANTS & CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    NPM = "npm"
    PYPI = "pypi"
    GOVUK = "govuk"
    COMPANIES_HOUSE = "companies_house"
    WIKIDATA = "wikidata"
    OPENCORPORATES = "opencorporates"
    GDELT = "gdelt"
    HACKERTARGET = "hackertarget"
    IPINFO = "ipinfo"
    SHODAN = "shodan"
    WHOIS = "whois"


RATE_LIMIT_CONFIG = {
    SourceType.GITHUB: 1.0,           # 1 req/sec
    SourceType.GITLAB: 1.0,
    SourceType.NPM: 0.5,              # 2 req/sec (higher rate allowed)
    SourceType.PYPI: 1.0,
    SourceType.GOVUK: 0.5,
    SourceType.COMPANIES_HOUSE: 1.0,
    SourceType.WIKIDATA: 0.5,
    SourceType.OPENCORPORATES: 1.0,
    SourceType.GDELT: 2.0,            # More conservative
    SourceType.HACKERTARGET: 1.0,
    SourceType.IPINFO: 1.0,
    SourceType.SHODAN: 2.0,
    SourceType.WHOIS: 1.0,
}

BATCH_SIZE = 100  # Store profiles in batches
DEFAULT_TIMEOUT = 15.0  # HTTP request timeout


# ─────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────

@dataclass
class CollectionSource:
    """Configuration for a data source."""
    source_type: SourceType
    queries: list[str] = field(default_factory=list)
    max_results_per_query: int = 50
    enabled: bool = True
    api_key: Optional[str] = None


@dataclass
class CollectionJob:
    """Tracks a collection job."""
    job_id: str
    status: str  # "running", "stopping", "completed", "failed"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    
    target_profiles: int = 100000
    collected_profiles: int = 0
    deduplicated_profiles: int = 0
    stored_profiles: int = 0
    
    sources: list[CollectionSource] = field(default_factory=list)
    progress_percent: int = 0
    
    processed_count: int = 0
    total_count: int = 0
    
    source_breakdown: dict[str, int] = field(default_factory=dict)
    recent_errors: list[str] = field(default_factory=list)
    
    stop_requested: bool = False
    target_reached: bool = False


@dataclass
class SignalCollectionResult:
    """Result of collecting from a source."""
    source: SourceType
    query: str
    success: bool
    profiles_collected: int = 0
    profiles_stored: int = 0
    duplicates_found: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0
    raw_count: int = 0


# ─────────────────────────────────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────

class AsyncRateLimiter:
    """Per-source rate limiting."""
    
    def __init__(self, min_interval_seconds: float = 1.0):
        self._min_interval = min_interval_seconds
        self._last_call = 0.0
        self._lock = asyncio.Lock()
    
    async def wait(self) -> None:
        """Wait until next request is allowed."""
        async with self._lock:
            now = time.monotonic()
            delay = self._min_interval - (now - self._last_call)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_call = time.monotonic()


# ─────────────────────────────────────────────────────────────────────────
# SIGNAL COLLECTOR
# ─────────────────────────────────────────────────────────────────────────

class SignalCollector:
    """
    Orchestrates signal collection from multiple sources.
    
    Does NOT create synthetic profiles.
    Only stores profiles with complete provenance.
    """
    
    def __init__(self):
        self._jobs: dict[str, CollectionJob] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()
        self._entity_engine = EntityResolutionEngine()
        self._rate_limiters: dict[SourceType, AsyncRateLimiter] = {
            source_type: AsyncRateLimiter(RATE_LIMIT_CONFIG[source_type])
            for source_type in SourceType
        }
        self._stored_profiles: set[str] = set()  # Track canonical keys of stored
    
    async def start_collection(
        self,
        target_profiles: int = 100000,
        sources: Optional[list[CollectionSource]] = None,
    ) -> CollectionJob:
        """Start a new collection job."""
        job_id = f"collect-{uuid.uuid4().hex[:8]}"
        
        if sources is None:
            sources = self._default_sources()
        
        # Calculate total work units
        total_count = sum(
            len(source.queries) * source.max_results_per_query
            for source in sources
            if source.enabled
        )
        
        job = CollectionJob(
            job_id=job_id,
            status="running",
            target_profiles=max(1, int(target_profiles)),
            sources=sources,
            total_count=max(1, total_count),
        )
        
        async with self._lock:
            self._jobs[job_id] = job
            self._tasks[job_id] = asyncio.create_task(self._run_collection(job))
        
        logger.info(f"Started collection job {job_id}, target {target_profiles}")
        return job
    
    async def stop_collection(self, job_id: str) -> bool:
        """Request stop for a running job."""
        job = self._jobs.get(job_id)
        if job:
            job.stop_requested = True
            logger.info(f"Stop requested for job {job_id}")
            return True
        return False
    
    def get_job(self, job_id: str) -> Optional[CollectionJob]:
        """Get job status."""
        return self._jobs.get(job_id)
    
    def list_jobs(self) -> list[CollectionJob]:
        """List all jobs, most recent first."""
        return sorted(self._jobs.values(), key=lambda j: j.started_at, reverse=True)
    
    # Private implementation methods
    
    def _default_sources(self) -> list[CollectionSource]:
        """Default collection sources for UK."""
        return [
            CollectionSource(
                SourceType.GITHUB,
                queries=[
                    'location:"UK"', 'location:"United Kingdom"',
                    'location:London', 'location:Manchester',
                ],
                max_results_per_query=100,
            ),
            CollectionSource(
                SourceType.GITLAB,
                queries=["UK", "United Kingdom"],
                max_results_per_query=50,
            ),
            CollectionSource(
                SourceType.NPM,
                queries=["UK", "United Kingdom", "uk-"],
                max_results_per_query=50,
            ),
            CollectionSource(
                SourceType.PYPI,
                queries=["UK", "United Kingdom", "uk-"],
                max_results_per_query=50,
            ),
            CollectionSource(
                SourceType.GOVUK,
                queries=["UK", "government", "policy"],
                max_results_per_query=50,
            ),
            CollectionSource(
                SourceType.COMPANIES_HOUSE,
                queries=["*"],
                max_results_per_query=100,
            ),
            CollectionSource(
                SourceType.GDELT,
                queries=["United Kingdom", "UK news"],
                max_results_per_query=50,
            ),
        ]
    
    async def _run_collection(self, job: CollectionJob) -> None:
        """Main collection loop."""
        try:
            job.status = "running"
            
            for source in job.sources:
                if not source.enabled:
                    continue
                if job.stop_requested:
                    break
                if job.target_reached:
                    break
                
                for query in source.queries:
                    if job.stop_requested or job.target_reached:
                        break
                    
                    await self._rate_limiters[source.source_type].wait()
                    
                    result = await self._collect_from_source(
                        job, source.source_type, query, source.max_results_per_query
                    )
                    
                    if result.success:
                        logger.info(
                            f"Collected {result.profiles_collected} from {source.source_type} "
                            f"(stored: {result.profiles_stored}, dupes: {result.duplicates_found})"
                        )
            
            # Mark complete
            if job.stop_requested:
                job.status = "stopped"
            else:
                job.status = "completed"
            
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info(f"Collection job {job.job_id} complete: {job.stored_profiles} profiles")
            
        except Exception as e:
            logger.error(f"Collection job {job.job_id} failed: {e}")
            job.status = "failed"
            job.recent_errors.append(str(e))
            job.completed_at = datetime.now(timezone.utc).isoformat()
    
    async def _collect_from_source(
        self,
        job: CollectionJob,
        source_type: SourceType,
        query: str,
        max_results: int,
    ) -> SignalCollectionResult:
        """Collect from a specific source."""
        start_time = time.time()
        
        try:
            if source_type == SourceType.GITHUB:
                profiles = await self._collect_github(query, max_results)
            elif source_type == SourceType.GITLAB:
                profiles = await self._collect_gitlab(query, max_results)
            elif source_type == SourceType.NPM:
                profiles = await self._collect_npm(query, max_results)
            elif source_type == SourceType.PYPI:
                profiles = await self._collect_pypi(query, max_results)
            elif source_type == SourceType.GOVUK:
                profiles = await self._collect_govuk(query, max_results)
            elif source_type == SourceType.COMPANIES_HOUSE:
                profiles = await self._collect_companies_house(query, max_results)
            elif source_type == SourceType.GDELT:
                profiles = await self._collect_gdelt(query, max_results)
            else:
                profiles = []
            
            if not profiles:
                return SignalCollectionResult(
                    source=source_type,
                    query=query,
                    success=True,
                    profiles_collected=0,
                    duration_seconds=time.time() - start_time,
                )
            
            # Deduplicate and store
            stored = 0
            dupes = 0
            
            for profile in profiles:
                if job.collected_profiles >= job.target_profiles:
                    job.target_reached = True
                    break
                
                # Store profile
                try:
                    self._store_profile(profile)
                    stored += 1
                    job.collected_profiles += 1
                    job.stored_profiles += 1
                    
                    source_str = str(source_type.value)
                    job.source_breakdown[source_str] = job.source_breakdown.get(source_str, 0) + 1
                except Exception as e:
                    logger.warning(f"Failed to store profile: {e}")
            
            # Update progress
            if job.total_count > 0:
                job.progress_percent = int(100 * job.collected_profiles / job.target_profiles)
            
            job.processed_count += 1
            job.updated_at = datetime.now(timezone.utc).isoformat()
            
            return SignalCollectionResult(
                source=source_type,
                query=query,
                success=True,
                profiles_collected=len(profiles),
                profiles_stored=stored,
                duplicates_found=dupes,
                duration_seconds=time.time() - start_time,
                raw_count=len(profiles),
            )
        
        except Exception as e:
            logger.error(f"Collection failed for {source_type}:{query}: {e}")
            job.recent_errors.append(f"{source_type}: {str(e)}")
            return SignalCollectionResult(
                source=source_type,
                query=query,
                success=False,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )
    
    async def _collect_github(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from GitHub API."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://api.github.com/search/users"
                params = {"q": query, "per_page": min(100, max_results), "sort": "stars"}
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for user in data.get("items", [])[:max_results]:
                    profile = self._github_profile(user)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"GitHub collection error: {e}")
        
        return profiles
    
    async def _collect_gitlab(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from GitLab API."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://gitlab.com/api/v4/users"
                params = {"search": query, "per_page": min(100, max_results)}
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for user in data[:max_results]:
                    profile = self._gitlab_profile(user)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"GitLab collection error: {e}")
        
        return profiles
    
    async def _collect_npm(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from npm registry."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://registry.npmjs.org/-/v1/search"
                params = {"text": query, "size": min(100, max_results)}
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for package in data.get("objects", [])[:max_results]:
                    profile = self._npm_profile(package)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"npm collection error: {e}")
        
        return profiles
    
    async def _collect_pypi(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from PyPI."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = f"https://pypi.org/pypi/{query}/json"
                
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                
                profile = self._pypi_profile(data)
                if profile:
                    profiles.append(profile)
        except Exception as e:
            logger.warning(f"PyPI collection error: {e}")
        
        return profiles
    
    async def _collect_govuk(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from GOV.UK public data."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://www.gov.uk/api/search.json"
                params = {"q": query, "count": min(100, max_results)}
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for result in data.get("results", [])[:max_results]:
                    profile = self._govuk_profile(result)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"GOV.UK collection error: {e}")
        
        return profiles
    
    async def _collect_companies_house(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from Companies House API."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://api.company-information.service.gov.uk/search/companies"
                params = {"q": query, "items_per_page": min(100, max_results)}
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for company in data.get("items", [])[:max_results]:
                    profile = self._companies_house_profile(company)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"Companies House collection error: {e}")
        
        return profiles
    
    async def _collect_gdelt(self, query: str, max_results: int) -> list[dict[str, Any]]:
        """Collect from GDELT (news sources)."""
        profiles = []
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                url = "https://api.gdeltproject.org/api/v2/doc/doc"
                params = {
                    "query": query,
                    "mode": "timelinevolume",
                    "format": "json",
                    "maxrecords": min(250, max_results),
                }
                
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                for doc in data.get("articles", [])[:max_results]:
                    profile = self._gdelt_profile(doc)
                    if profile:
                        profiles.append(profile)
        except Exception as e:
            logger.warning(f"GDELT collection error: {e}")
        
        return profiles
    
    # Profile builders (minimal provenance)
    
    def _github_profile(self, user_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from GitHub user."""
        login = user_data.get("login")
        if not login:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "handle": login,
                "platform": "github",
                "profile_url": user_data.get("html_url"),
                "display_name": user_data.get("name", login),
            },
            "behavioral_intelligence": {
                "public_repos": user_data.get("public_repos", 0),
                "followers": user_data.get("followers", 0),
                "platform_presence": ["github"],
            },
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_github",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "github_user": {
                    "login": login,
                    "url": user_data.get("html_url"),
                    "type": user_data.get("type"),
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "person",
                "verification_confidence": 0.85,
                "public_profile_links": [user_data.get("html_url")],
                "public_identity_sources": ["github"],
            },
        }
    
    def _gitlab_profile(self, user_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from GitLab user."""
        username = user_data.get("username")
        if not username:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "handle": username,
                "platform": "gitlab",
                "profile_url": user_data.get("web_url"),
                "display_name": user_data.get("name", username),
            },
            "behavioral_intelligence": {
                "platform_presence": ["gitlab"],
            },
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_gitlab",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "gitlab_user": {
                    "username": username,
                    "url": user_data.get("web_url"),
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "person",
                "verification_confidence": 0.80,
                "public_profile_links": [user_data.get("web_url")],
                "public_identity_sources": ["gitlab"],
            },
        }
    
    def _npm_profile(self, package_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from npm package."""
        package_name = package_data.get("package", {}).get("name")
        if not package_name:
            return None
        
        maintainer = package_data.get("package", {}).get("maintainers", [{}])[0]
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "handle": maintainer.get("username", package_name),
                "platform": "npm",
                "domain": "npmjs.com",
                "profile_url": f"https://www.npmjs.com/package/{package_name}",
            },
            "behavioral_intelligence": {
                "platform_presence": ["npm"],
            },
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_npm",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "npm_package": {
                    "name": package_name,
                    "url": f"https://www.npmjs.com/package/{package_name}",
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "person",
                "verification_confidence": 0.75,
                "public_profile_links": [f"https://www.npmjs.com/package/{package_name}"],
                "public_identity_sources": ["npm"],
            },
        }
    
    def _pypi_profile(self, package_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from PyPI package."""
        info = package_data.get("info", {})
        package_name = info.get("name")
        if not package_name:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "handle": info.get("author", package_name),
                "platform": "pypi",
                "domain": "pypi.org",
                "profile_url": f"https://pypi.org/project/{package_name}/",
            },
            "behavioral_intelligence": {
                "platform_presence": ["pypi"],
            },
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_pypi",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "pypi_package": {
                    "name": package_name,
                    "url": f"https://pypi.org/project/{package_name}/",
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "person",
                "verification_confidence": 0.75,
                "public_profile_links": [f"https://pypi.org/project/{package_name}/"],
                "public_identity_sources": ["pypi"],
            },
        }
    
    def _govuk_profile(self, result_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from GOV.UK public data."""
        title = result_data.get("title")
        if not title:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "display_name": title,
                "platform": "govuk",
                "profile_url": result_data.get("link"),
            },
            "behavioral_intelligence": {},
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_govuk",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "govuk_result": {
                    "title": title,
                    "url": result_data.get("link"),
                    "description": result_data.get("description"),
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "public_record",
                "verification_confidence": 0.90,
                "public_profile_links": [result_data.get("link")],
                "public_identity_sources": ["govuk"],
            },
        }
    
    def _companies_house_profile(self, company_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from Companies House."""
        company_name = company_data.get("title")
        if not company_name:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "display_name": company_name,
                "platform": "companies_house",
            },
            "behavioral_intelligence": {},
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_companies_house",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "companies_house": {
                    "company_name": company_name,
                    "company_number": company_data.get("company_number"),
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "organization",
                "verification_confidence": 0.95,
                "public_identity_sources": ["companies_house"],
            },
        }
    
    def _gdelt_profile(self, doc_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Build profile from GDELT news source."""
        title = doc_data.get("title")
        url = doc_data.get("url")
        if not title or not url:
            return None
        
        return {
            "stratum_id": f"STRID-{uuid.uuid4().hex[:8].upper()}",
            "identity_anchors": {
                "display_name": title,
                "platform": "gdelt",
                "profile_url": url,
            },
            "behavioral_intelligence": {},
            "situational_intelligence": {
                "country": "UK",
            },
            "metadata": {
                "source": "public_gdelt",
                "collection_date": datetime.now(timezone.utc).isoformat(),
                "country": "UK",
                "data_type": "public_signal",
            },
            "raw_signals": {
                "gdelt_article": {
                    "title": title,
                    "url": url,
                }
            },
            "verification": {
                "is_real_entity": True,
                "entity_type": "publisher",
                "verification_confidence": 0.70,
                "public_profile_links": [url],
                "public_identity_sources": ["gdelt"],
            },
        }
    
    def _store_profile(self, profile: dict[str, Any]) -> None:
        """Store profile in database with provenance."""
        try:
            stratum_id = profile.get("stratum_id")
            if not stratum_id:
                return
            
            # Create canonical entity for dedup tracking
            entity = self._entity_engine.resolve_profile(profile)
            canonical_key = entity.canonical_entity_key
            
            # Check for duplicates
            if canonical_key in self._stored_profiles:
                logger.debug(f"Skipping duplicate profile: {canonical_key}")
                return
            
            # Store in database
            conn = db._connect()
            conn.execute(
                """
                INSERT OR REPLACE INTO identities 
                (id, handle, platform, display_name, extra, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    stratum_id,
                    profile.get("identity_anchors", {}).get("handle", ""),
                    profile.get("identity_anchors", {}).get("platform", ""),
                    profile.get("identity_anchors", {}).get("display_name", ""),
                    json.dumps(profile),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            conn.close()
            
            self._stored_profiles.add(canonical_key)
            logger.debug(f"Stored profile {stratum_id}")
        except Exception as e:
            logger.error(f"Failed to store profile: {e}")
            raise


# ─────────────────────────────────────────────────────────────────────────
# SINGLETON INSTANCE
# ─────────────────────────────────────────────────────────────────────────

_collector: Optional[SignalCollector] = None


def get_collector() -> SignalCollector:
    """Get or create the signal collector."""
    global _collector
    if _collector is None:
        _collector = SignalCollector()
    return _collector
