"""
Safe STRATUM OMNIS architecture blueprint.

This mirrors the structure described in the supplied STRATUM OMNIS documents
while keeping sensitive/private collection surfaces disabled or stubbed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ...database import db
from ..uk_signal_collector import collector
from .profile_store import load_stratum_profiles, source_breakdown


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class StratumLayer:
    layer_id: str
    title: str
    primary_technology: str
    function: str
    implementation_status: str
    safety_mode: str
    implementation_notes: str


@dataclass(frozen=True)
class SignalSource:
    source_id: str
    name: str
    category: str
    collection_mechanism: str
    implementation_status: str
    safety_mode: str
    notes: str


LAYERS: tuple[StratumLayer, ...] = (
    StratumLayer("L0", "Signal Sources", "Public APIs + safe adapters", "Source signal catalog and governance", "implemented", "safe_public_only", "Document-aligned public adapters are live for GDELT, OpenStreetMap, GOV.UK, public spending context, hostsearch, IPInfo, and allowlisted WHOIS. GitHub/GitLab/npm/PyPI remain optional public supplements. Sensitive/private streams remain explicit disabled stubs."),
    StratumLayer("L1", "Collection Infrastructure", "Async collectors + background jobs", "Collect source data with rate limiting and guardrails", "implemented", "safe_public_only", "UK public signal collector now runs across public event, geospatial, official registry, hostname, and optional developer-ecosystem sources."),
    StratumLayer("L2", "Stream Processing", "Event bus + normalized stream views", "Turn raw signals into normalized behavioral events", "implemented", "safe_public_only", "A stream-processing module builds normalized event envelopes and runtime stream summaries from live STRATUM profiles and the JULIUS event bus."),
    StratumLayer("L3", "Identity Resolution Engine", "SQLite identities + STRATUM identity spine", "Persist and correlate profiles under a shared identity spine", "implemented", "safe_public_only", "Identity-resolution views now derive anchor groups, platform distributions, and IP-linked associations from real stored STRATUM profiles."),
    StratumLayer("L4", "Feature Store", "Profile-backed engineered features", "Hold engineered features per identity", "implemented", "safe_public_only", "A feature-store snapshot now derives structured feature vectors from live STRATUM profiles."),
    StratumLayer("L5", "Model Hub", "Feature + Oracle + CSIE registry", "Run scoring and enrichment models over stored identities", "implemented", "safe_public_only", "A model-hub registry now exposes live feature-store, ORACLE, and CSIE outputs over real public profiles."),
    StratumLayer("L6", "ORACLE Engine", "Heuristic multi-horizon predictions", "Multi-horizon prediction and next-action synthesis", "implemented", "safe_public_only", "A safe ORACLE-style prediction layer is live over public profiles with 24h/7d/30d horizons."),
    StratumLayer("L7", "Product API Gateway", "FastAPI routers", "Expose collection, status, export, and blueprint endpoints", "implemented", "safe_public_only", "API endpoints are live for collection control, export, and STRATUM blueprint inspection."),
    StratumLayer("L8", "Client Platform", "React + TypeScript", "Visualize signals, architecture, and progress", "implemented", "safe_public_only", "Signal collection and STRATUM architecture panels are available in the frontend."),
)


SIGNAL_SOURCES: tuple[SignalSource, ...] = (
    SignalSource("gdelt_public_events", "GDELT Public Event / News Feed", "macro_environmental_context", "GDELT DOC API", "implemented", "safe_public_only", "Collects public UK event/news article metadata without credentials."),
    SignalSource("openstreetmap_public_places", "OpenStreetMap Public Places", "geospatial_context", "Nominatim public search API", "implemented", "safe_public_only", "Collects public UK place/geospatial context records."),
    SignalSource("govuk_public_registry", "GOV.UK Public Content Registry", "public_records", "GOV.UK search API", "implemented", "safe_public_only", "Collects official public GOV.UK content records by query."),
    SignalSource("public_spending_context", "Public Spending Context", "public_records", "GOV.UK public search metadata", "implemented", "safe_public_only", "Collects public procurement/spending-context records and stores only public metadata plus derived scores."),
    SignalSource("hackertarget_hostsearch", "Hackertarget Hostsearch", "public_records", "Public hostname discovery by UK suffix", "implemented", "safe_public_only", "Collects real public UK hostnames and IP associations without active scanning."),
    SignalSource("ipinfo_geocontext", "IPInfo Public Geocontext", "geospatial_context", "Public IP org/city/region lookup", "implemented", "safe_public_only", "Adds real public geocontext for discovered IP anchors."),
    SignalSource("allowlisted_whois", "Allowlisted WHOIS", "public_records", "Explicit domain WHOIS lookup", "implemented", "safe_public_only", "Runs only for domains provided by the operator."),
    SignalSource("github_public_profiles", "GitHub Public Profiles", "digital_behavioral_supplement", "GitHub search/users API", "implemented_optional", "safe_public_only", "Present in the supplied architecture document and available only when explicit GitHub queries are supplied."),
    SignalSource("gitlab_public_profiles", "GitLab Public Profiles", "digital_behavioral_supplement", "GitLab public users API", "implemented_optional", "safe_public_only", "Optional public developer-profile supplement by configured search terms."),
    SignalSource("npm_public_packages", "npm Public Packages", "digital_behavioral_supplement", "npm registry search API", "implemented_optional", "safe_public_only", "Optional public package metadata collection."),
    SignalSource("pypi_public_packages", "PyPI Public Packages", "digital_behavioral_supplement", "PyPI package JSON API", "implemented_optional", "safe_public_only", "Optional public Python package metadata collection."),
    SignalSource("newsapi_public_news", "NewsAPI Public News", "macro_environmental_context", "NewsAPI connector", "stubbed", "requires_api_key", "Mentioned in the supplied architecture document, but not enabled because it requires an API key and terms review."),
    SignalSource("reuters_connect_news", "Reuters Connect", "macro_environmental_context", "Licensed Reuters connector", "stubbed", "requires_license", "Mentioned in the supplied architecture document, but not enabled because it requires licensed access."),
    SignalSource("telco_network_layer", "Telco Network Layer", "telco_network_behavioral", "On-prem telco agent", "stubbed", "disabled", "Not implemented due sensitivity and private-data constraints."),
    SignalSource("upi_financial_transactions", "UPI Financial Signals", "financial_transaction_behavioral", "Consent-gated financial ingestion", "stubbed", "disabled", "Not implemented; financial credentialed data is intentionally out of scope."),
    SignalSource("physical_world_edge_ai", "Physical World Edge-AI", "physical_world_behavioral", "CCTV/NVR edge inference", "stubbed", "disabled", "Not implemented; physical surveillance ingestion is out of scope."),
    SignalSource("social_graph_metadata", "Social Graph Metadata", "social_graph_influence", "Call graph / relational metadata", "stubbed", "disabled", "No private social graph ingestion is implemented."),
    SignalSource("biometric_health", "Biometric / Health Signals", "biometric_health_behavioral", "Opt-in wearable or device telemetry", "stubbed", "disabled", "Not implemented; high-sensitivity personal data is excluded."),
    SignalSource("geopolitical_event_feed", "Geopolitical Event Feed", "macro_environmental_context", "Public event/news feeds", "implemented", "safe_public_only", "GDELT public-event metadata is now fused into STRATUM identities."),
    SignalSource("local_incident_feed", "Local Incident Feed", "micro_event_context", "Public incident APIs", "scaffolded", "safe_public_only", "Can be attached later through existing monitor/globe feeds."),
    SignalSource("public_records_batch", "Public Records Batch", "public_records", "Batch import from public registries", "scaffolded", "safe_public_only", "No import connector yet; only architecture placeholder."),
    SignalSource("digital_behavioral_publishers", "Digital Behavioral Publishers", "digital_behavioral_supplement", "Publisher SDK / pixel", "stubbed", "disabled", "No SDK ingestion is implemented."),
    SignalSource("cross_border_signals", "Cross-Border Signals", "cross_border_behavioral", "Partner APIs and remittance feeds", "stubbed", "disabled", "Not implemented due sensitivity and external dependencies."),
)
def _recent_job_snapshots(limit: int = 5) -> list[dict[str, Any]]:
    live_jobs = [collector.serialize_job(job) for job in collector.list_jobs()[:limit]]
    if live_jobs:
        return live_jobs

    profiles = load_stratum_profiles()
    job_ids: list[str] = []
    for profile in profiles:
        job_id = str((profile.get("metadata") or {}).get("collection_job_id") or "")
        if job_id and job_id not in job_ids:
            job_ids.append(job_id)
        if len(job_ids) >= limit:
            break

    snapshots: list[dict[str, Any]] = []
    for job_id in job_ids:
        snapshot = collector.get_job_snapshot(job_id)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots


def get_stratum_blueprint() -> dict[str, Any]:
    return {
        "name": "STRATUM OMNIS",
        "version": "safe-architecture-v1",
        "generated_at": _utcnow(),
        "source_documents": [
            "STRATUM_OMNIS_TechArch (2).docx",
            "STRATUM_OMNIS_Entity (1).docx",
            "CSIE_Technical_Specification.docx",
        ],
        "mode": "safe_public_only",
        "doc_alignment": {
            "strategy": "Follow the STRATUM layer and signal boundaries from the documents.",
            "guardrails": [
                "Public-source collection only for active adapters.",
                "Sensitive/private signals remain explicit stubs.",
                "No credential harvesting, public service scanning, or mass vulnerability collection.",
            ],
        },
        "layers": [asdict(layer) for layer in LAYERS],
        "signal_sources": [asdict(source) for source in SIGNAL_SOURCES],
        "next_build_targets": [
            "Add more official open registries when stable unauthenticated APIs are available.",
            "Add optional authenticated adapters only for sources the operator owns or has permission to use.",
            "Persist STRATUM feature rows in a dedicated feature table when SQLite migrations are next expanded.",
        ],
    }


def get_stratum_runtime() -> dict[str, Any]:
    stats = db.get_system_stats()
    profiles = load_stratum_profiles()
    job_snapshots = _recent_job_snapshots()
    public_active = sum(1 for source in SIGNAL_SOURCES if source.implementation_status == "implemented")
    stubbed = sum(1 for source in SIGNAL_SOURCES if source.implementation_status == "stubbed")

    return {
        "generated_at": _utcnow(),
        "mode": "safe_public_only",
        "stats": {
            **stats,
            "stratum_profiles": len(profiles),
            "source_breakdown": source_breakdown(profiles),
            "implemented_signal_sources": public_active,
            "stubbed_signal_sources": stubbed,
        },
        "runtime": {
            "active_layers": [layer.layer_id for layer in LAYERS if layer.implementation_status in {"implemented", "partial"}],
            "recent_jobs": job_snapshots,
            "latest_profiles": profiles[:5],
        },
    }
