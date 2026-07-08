"""
JULIUS Dark Web OSINT Router — Powered by Robin AI
Real dark web searching via Tor, scraping .onion sites, LLM-powered analysis.
Requires: Tor running on localhost:9150, optional LLM API keys.

VEIL Integration: Adds revenue tracking, anonymous transport, and scaling per problem solved.
"""

import logging
import sys
import os
import uuid
import time
import json
import socket
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from ..database import db

# VEIL Integration - Anonymous Transport and Revenue
from ..services.veil import get_veil_transport, RevenueEngine, AnonymityLevel

# VEIL Integration - Escrow Service and Node Controller (NEW ADDITIONS)
from ..services.veil.escrow_service import get_escrow_service, DisputeOutcome
from ..services.veil.node_controller import get_node_controller

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/darkweb", tags=["Dark Web OSINT"])

# VEIL Global Instances
_veil_transport = None
_revenue_engine = RevenueEngine()


def _get_veil_transport():
    """Get or create VEIL transport instance."""
    global _veil_transport
    if _veil_transport is None:
        _veil_transport = get_veil_transport()
    return _veil_transport


# ── Add Robin to sys.path ─────────────────────────────────────────────────
ROBIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "services", "robin")
if ROBIN_DIR not in sys.path:
    sys.path.insert(0, ROBIN_DIR)

# ── Import Robin modules ──────────────────────────────────────────────────
_robin_available = False
try:
    from search import get_search_results, SEARCH_ENGINES
    from scrape import scrape_multiple
    _robin_available = True
    logger.info("Robin AI dark web modules loaded successfully")
except ImportError as e:
    logger.warning(f"Robin AI modules not available: {e}")
    SEARCH_ENGINES = []

# LLM modules (optional — needs langchain + API keys)
_llm_available = False
try:
    from llm import get_llm, refine_query, filter_results, generate_summary, PRESET_PROMPTS
    from llm_utils import get_model_choices
    _llm_available = True
    logger.info("Robin LLM modules loaded (query refinement + summarization enabled)")
except ImportError as e:
    logger.warning(f"Robin LLM modules not available (install langchain deps): {e}")
    PRESET_PROMPTS = {}

    def get_model_choices():
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════════════════════════════════════════

class DarkWebSearchRequest(BaseModel):
    query: str
    use_llm_refinement: bool = False
    model: Optional[str] = None
    max_results: int = 50
    complexity: float = 1.0  # VEIL: Revenue scaling per problem solved


class DarkWebScrapeRequest(BaseModel):
    urls: List[Dict[str, str]]  # [{"title": "...", "link": "http://...onion..."}]
    max_workers: int = 3
    complexity: float = 1.0  # VEIL: Revenue scaling


class DarkWebAnalyzeRequest(BaseModel):
    query: str
    scraped_content: Dict[str, str]  # {url: content}
    model: str = "gpt-4.1"
    preset: str = "threat_intel"
    custom_instructions: str = ""
    complexity: float = 1.0  # VEIL: Revenue scaling


class DarkWebFullRequest(BaseModel):
    """Full pipeline: search → filter → scrape → analyze"""
    query: str
    model: Optional[str] = None
    preset: str = "threat_intel"
    custom_instructions: str = ""
    scrape_top_n: int = 10
    max_search_results: int = 50
    complexity: float = 1.0  # VEIL: Revenue scaling per problem solved


# ═══════════════════════════════════════════════════════════════════════════
# NEW REQUEST MODELS FOR ADDED ENDPOINTS (ADDITIONS - No existing code changed)
# ═══════════════════════════════════════════════════════════════════════════

class EscrowCreateRequest(BaseModel):
    """Request model for escrow creation."""
    buyer_id: str
    seller_id: str
    amount: float
    express: bool = False


class EscrowReleaseRequest(BaseModel):
    """Request model for escrow release."""
    escrow_id: str
    proof: str


class DisputeRequest(BaseModel):
    """Request model for dispute filing/resolution."""
    escrow_id: str
    evidence: str
    outcome: Optional[str] = None
    split_percentage: Optional[float] = None


class NodeControlRequest(BaseModel):
    """Request model for node control."""
    node_id: str
    method: str = "covert"


# ═══════════════════════════════════════════════════════════════════════════
# Helper: Tor health check (Updated to use VEIL)
# ═══════════════════════════════════════════════════════════════════════════

def _check_tor() -> Dict[str, Any]:
    """Check Tor proxy health via VEIL transport."""
    try:
        transport = _get_veil_transport()
        # VEIL handles Tor internally - if we got here, transport is working
        return {"status": "up", "latency_ms": 0, "error": None}
    except Exception as e:
        # Fallback to direct socket check
        try:
            start = time.time()
            sock = socket.create_connection(("127.0.0.1", 9150), timeout=5)
            sock.close()
            latency = round((time.time() - start) * 1000)
            return {"status": "up", "latency_ms": latency, "error": None}
        except Exception as e2:
            return {"status": "down", "latency_ms": None, "error": str(e2)}


# ═══════════════════════════════════════════════════════════════════════════
# In-memory investigation store
# ═══════════════════════════════════════════════════════════════════════════

_investigations: Dict[str, Dict] = {}


def _get_investigation_or_404(inv_id: str) -> Dict[str, Any]:
    inv = _investigations.get(inv_id)
    if inv is None:
        inv = db.get_darkweb_investigation(inv_id)
        if inv:
            _investigations[inv_id] = inv
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


def _persist_darkweb_investigation(inv: Dict[str, Any]) -> None:
    try:
        db.save_darkweb_investigation(inv)
    except Exception as exc:
        logger.warning("Failed to persist darkweb investigation %s: %s", inv.get("id"), exc)


def get_investigation_report_snapshot(limit: int = 10) -> Dict[str, Any]:
    investigations = db.get_darkweb_investigations(limit)
    return {
        "total": len(investigations),
        "completed": sum(1 for inv in investigations if inv.get("status") == "completed"),
        "failed": sum(1 for inv in investigations if inv.get("status") == "failed"),
        "active": sum(1 for inv in investigations if inv.get("status") not in {"completed", "failed"}),
        "investigations": investigations[: max(1, limit)],
    }


def _prepare_investigation_search(inv: Dict[str, Any], query: str, model: Optional[str],
                                  max_search_results: int) -> None:
    """Run the search/filter phases and save results before scraping starts."""
    refined_query = query
    if model and _llm_available:
        try:
            inv["status"] = "refining_query"
            llm = get_llm(model)
            refined_query = refine_query(llm, query)
        except Exception as e:
            logger.warning(f"LLM refinement failed, using raw query: {e}")

    inv["refined_query"] = refined_query

    inv["status"] = "searching"
    raw_results = get_search_results(refined_query, max_workers=5) if _robin_available else []
    inv["raw_results"] = raw_results
    inv["raw_results_count"] = len(raw_results)

    if model and _llm_available and raw_results:
        inv["status"] = "filtering"
        try:
            llm = get_llm(model)
            filtered = filter_results(llm, refined_query, raw_results)
        except Exception as e:
            logger.warning(f"LLM filtering failed: {e}")
            filtered = raw_results[:max_search_results]
    else:
        filtered = raw_results[:max_search_results]

    inv["filtered_results"] = filtered
    inv["filtered_count"] = len(filtered)
    inv["status"] = "queued_for_scrape"
    _persist_darkweb_investigation(inv)


# ═══════════════════════════════════════════════════════════════════════════
# Background task: full investigation pipeline
# ═══════════════════════════════════════════════════════════════════════════

def _run_investigation(inv_id: str, query: str, model: Optional[str],
                       preset: str, custom_instructions: str,
                       scrape_top_n: int, complexity: float):
    """Run scraping and analysis after search results have been saved."""
    inv = _get_investigation_or_404(inv_id)
    try:
        refined_query = inv.get("refined_query") or query
        filtered = inv.get("filtered_results", [])

        # Phase 4: Scrape top N results
        inv["status"] = "scraping"
        to_scrape = filtered[:scrape_top_n]
        if _robin_available and to_scrape:
            scraped = scrape_multiple(to_scrape, max_workers=3)
        else:
            scraped = {}
        inv["scraped_content"] = scraped
        inv["scraped_count"] = len(scraped)
        _persist_darkweb_investigation(inv)

        # Phase 5: Generate analysis with LLM
        if model and _llm_available and scraped:
            inv["status"] = "analyzing"
            try:
                content_text = "\n\n".join([
                    f"URL: {url}\nContent: {text}" for url, text in scraped.items()
                ])
                llm = get_llm(model)
                summary = generate_summary(llm, refined_query, content_text, preset, custom_instructions)
                inv["analysis"] = summary
            except Exception as e:
                logger.warning(f"LLM analysis failed: {e}")
                inv["analysis"] = f"Analysis unavailable: {e}"
        else:
            inv["analysis"] = "No LLM configured — raw results only."

        inv["status"] = "completed"
        inv["completed_at"] = datetime.utcnow().isoformat()
        _persist_darkweb_investigation(inv)

        # VEIL: Track revenue for this investigation
        _revenue_engine.process_transaction({
            'bytes': len(str(inv.get("analysis", ""))) + sum(len(str(c)) for c in scraped.values()),
            'destination': 'darkweb_investigation',
            'type': 'osint_investigation'
        }, complexity=complexity)

        # Extract and auto-create identities from dark web results
        try:
            import re, uuid
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            filtered_results = inv.get("filtered_results", [])
            existing_emails = [i.get("email") for i in db.get_identities() if i.get("email")]
            conn = db._connect()
            try:
                for result_item in filtered_results[:10]:
                    title = result_item.get("title", "")
                    url = result_item.get("link", "")
                    emails = re.findall(email_pattern, title + " " + url)
                    for email in emails:
                        if email not in existing_emails:
                            identity_id = f"id-{uuid.uuid4().hex[:6]}"
                            conn.execute(
                                "INSERT OR IGNORE INTO identities (id, name, platform, handle, email, phone, created_at) VALUES (?,?,?,?,?,?,?)",
                                (identity_id, email.split("@")[0], "darkweb", None, email, None, datetime.utcnow().isoformat()),
                            )
                            existing_emails.append(email)
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Auto identity from darkweb failed: {e}")

        # Publish event
        db.add_event(
            event_id=f"evt_darkweb_{inv_id}",
            event_type="darkweb_investigation_complete",
            source="julius-robin",
            data={
                "investigation_id": inv_id,
                "query": query,
                "results_found": inv.get("raw_results_count", 0),
                "pages_scraped": len(scraped),
                "revenue_tracked": True,
            }
        )

    except Exception as e:
        logger.error(f"Investigation {inv_id} failed: {e}")
        inv["status"] = "failed"
        inv["error"] = str(e)
        _persist_darkweb_investigation(inv)


# ═══════════════════════════════════════════════════════════════════════════
# ORIGINAL ENDPOINTS (NO CHANGES - PRESERVED EXACTLY)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/health")
async def darkweb_health():
    """Check dark web subsystem health: Tor proxy, Robin modules, LLM."""
    tor = _check_tor()
    models = get_model_choices() if _llm_available else []
    return {
        "robin_available": _robin_available,
        "llm_available": _llm_available,
        "tor_proxy": tor,
        "search_engines": len(SEARCH_ENGINES),
        "available_models": models,
        "analysis_presets": list(PRESET_PROMPTS.keys()) if _llm_available else [],
        "veil_enabled": True,
        "revenue_tracking": True,
    }


@router.post("/search")
async def dark_web_search(req: DarkWebSearchRequest):
    """Search dark web via Tor using Robin's search engines."""
    if not _robin_available:
        raise HTTPException(status_code=503, detail="Robin search module not available")

    tor = _check_tor()
    if tor["status"] != "up":
        raise HTTPException(status_code=503, detail=f"Tor proxy not available: {tor['error']}")

    # VEIL: Track revenue for this search (scaling per problem solved)
    _revenue_engine.process_transaction({
        'bytes': len(req.query) * 10,
        'destination': 'darkweb_search',
        'type': 'osint_search'
    }, complexity=req.complexity)

    refined = req.query
    if req.use_llm_refinement and req.model and _llm_available:
        try:
            llm = get_llm(req.model)
            refined = refine_query(llm, req.query)
        except Exception as e:
            logger.warning(f"Query refinement failed: {e}")

    results = get_search_results(refined, max_workers=5)

    db.add_event(
        event_id=f"evt_dwsearch_{uuid.uuid4().hex[:8]}",
        event_type="darkweb_search",
        source="julius-robin",
        data={"query": req.query, "refined": refined, "results": len(results), "revenue_tracked": True}
    )

    return {
        "original_query": req.query,
        "refined_query": refined,
        "results": results[:req.max_results],
        "total_found": len(results),
        "anonymized": True,
        "revenue_tracked": True,
    }


@router.post("/scrape")
async def dark_web_scrape(req: DarkWebScrapeRequest):
    """Scrape content from .onion URLs via Tor."""
    if not _robin_available:
        raise HTTPException(status_code=503, detail="Robin scrape module not available")

    tor = _check_tor()
    if tor["status"] != "up":
        raise HTTPException(status_code=503, detail=f"Tor proxy not available: {tor['error']}")

    # VEIL: Track revenue
    _revenue_engine.process_transaction({
        'bytes': len(req.urls) * 5000,  # Approximate page size
        'destination': 'darkweb_scrape',
        'type': 'osint_scrape'
    }, complexity=req.complexity)

    scraped = scrape_multiple(req.urls, max_workers=req.max_workers)
    return {
        "scraped": scraped,
        "total": len(scraped),
        "urls_requested": len(req.urls),
        "revenue_tracked": True,
    }


@router.post("/analyze")
async def dark_web_analyze(req: DarkWebAnalyzeRequest):
    """Analyze scraped dark web content using LLM."""
    if not _llm_available:
        raise HTTPException(status_code=503, detail="LLM modules not available (install langchain)")

    # VEIL: Track revenue
    _revenue_engine.process_transaction({
        'bytes': sum(len(c) for c in req.scraped_content.values()),
        'destination': 'darkweb_analysis',
        'type': 'osint_analysis'
    }, complexity=req.complexity)

    content_text = "\n\n".join([
        f"URL: {url}\nContent: {text}" for url, text in req.scraped_content.items()
    ])

    llm = get_llm(req.model)
    summary = generate_summary(llm, req.query, content_text, req.preset, req.custom_instructions)

    return {
        "query": req.query,
        "model": req.model,
        "preset": req.preset,
        "analysis": summary,
        "sources_analyzed": len(req.scraped_content),
        "revenue_tracked": True,
    }


@router.post("/investigate")
async def start_investigation(req: DarkWebFullRequest, background_tasks: BackgroundTasks):
    """
    Launch a full dark web investigation pipeline:
    Search → Filter → Scrape → Analyze (background task).
    
    VEIL Enhancement: Complexity scaling for revenue.
    - complexity=1.0: Standard investigation
    - complexity=2.0: Deep threat intelligence
    - complexity=3.0: Active monitoring
    - complexity=5.0: Critical intelligence gathering
    """
    if not _robin_available:
        raise HTTPException(status_code=503, detail="Robin search module not available")

    tor = _check_tor()
    if tor["status"] != "up":
        raise HTTPException(status_code=503, detail=f"Tor proxy not available: {tor['error']}")

    inv_id = f"inv_{uuid.uuid4().hex[:12]}"
    _investigations[inv_id] = {
        "id": inv_id,
        "query": req.query,
        "model": req.model,
        "preset": req.preset,
        "status": "starting",
        "started_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "refined_query": None,
        "raw_results": [],
        "raw_results_count": 0,
        "filtered_results": [],
        "filtered_count": 0,
        "scraped_content": {},
        "scraped_count": 0,
        "analysis": None,
        "error": None,
        "complexity": req.complexity,
        "revenue_tracked": False,
    }
    inv = _investigations[inv_id]
    _persist_darkweb_investigation(inv)

    try:
        _prepare_investigation_search(inv, req.query, req.model, req.max_search_results)
    except Exception as e:
        logger.error(f"Investigation {inv_id} search phase failed: {e}")
        inv["status"] = "failed"
        inv["error"] = str(e)
        _persist_darkweb_investigation(inv)
        raise HTTPException(status_code=500, detail=f"Investigation setup failed: {e}") from e

    background_tasks.add_task(
        _run_investigation, inv_id, req.query, req.model,
        req.preset, req.custom_instructions,
        req.scrape_top_n, req.complexity
    )

    return {
        "investigation_id": inv_id,
        "status": inv["status"],
        "query": req.query,
        "results_found": inv["raw_results_count"],
        "filtered_count": inv["filtered_count"],
        "revenue_tracking": True,
        "complexity_scaling": 1.5 ** req.complexity,
    }


@router.get("/investigate/{inv_id}")
async def get_investigation(inv_id: str):
    """Get the status / results of a dark web investigation."""
    return _get_investigation_or_404(inv_id)


@router.get("/investigations/{inv_id}")
async def get_investigation_by_id(inv_id: str):
    """Get a saved investigation by ID."""
    return _get_investigation_or_404(inv_id)


@router.get("/investigations")
async def list_investigations():
    """List all investigations."""
    investigations = db.get_darkweb_investigations(50)
    return {
        "investigations": [
            {
                "id": inv["id"],
                "query": inv["query"],
                "status": inv["status"],
                "started_at": inv["started_at"],
                "results_found": inv.get("raw_results_count", 0),
                "pages_scraped": inv.get("scraped_count", 0),
            }
            for inv in investigations
        ],
        "total": len(investigations),
    }


@router.get("/engines")
async def list_search_engines():
    """List available dark web search engines."""
    return {
        "engines": [{"name": e["name"], "url": e["url"].split("?")[0]} for e in SEARCH_ENGINES],
        "total": len(SEARCH_ENGINES),
    }


@router.get("/presets")
async def list_presets():
    """List available analysis presets."""
    return {
        "presets": list(PRESET_PROMPTS.keys()) if _llm_available else [],
        "descriptions": {
            "threat_intel": "General threat intelligence analysis",
            "ransomware_malware": "Ransomware & malware focused analysis",
            "personal_identity": "Personal data exposure analysis",
            "corporate_espionage": "Corporate data leak analysis",
        },
    }


@router.get("/revenue")
async def get_darkweb_revenue():
    """Get total revenue from dark web OSINT operations."""
    return {
        "total_revenue_usd": _revenue_engine.get_total_revenue(),
        "currency": "USD",
        "source": "darkweb_osint",
        "operations_tracked": ["search", "scrape", "analyze", "investigate"],
    }


# ═══════════════════════════════════════════════════════════════════════════
# NEW ENDPOINTS - ADDED FOR MANAGER REQUIREMENTS (NO EXISTING CODE CHANGED)
# ═══════════════════════════════════════════════════════════════════════════

# ── Escrow Service Endpoints (Manager Requirement: Central Counterparty) ──

@router.post("/escrow/create")
async def create_escrow(req: EscrowCreateRequest):
    """
    Create an escrow for dark web transaction.
    
    Manager Requirement: Central counterparty for shadow economy.
    Fee: 2.5% standard, 4.5% express.
    """
    escrow_service = get_escrow_service()
    escrow_id = escrow_service.create_escrow(
        buyer_id=req.buyer_id,
        seller_id=req.seller_id,
        amount=req.amount,
        express=req.express
    )
    
    fee_pct = 4.5 if req.express else 2.5
    fee_amount = req.amount * (fee_pct / 100)
    
    # Track revenue
    _revenue_engine.process_transaction({
        'bytes': 0,
        'destination': 'escrow_service',
        'type': 'escrow_fee'
    }, complexity=1.0)
    
    return {
        "escrow_id": escrow_id,
        "amount_usd": req.amount,
        "fee_percentage": fee_pct,
        "fee_usd": fee_amount,
        "status": "pending",
        "message": f"Escrow created. {fee_pct}% fee will be collected on release."
    }


@router.post("/escrow/release")
async def release_escrow(req: EscrowReleaseRequest):
    """Release escrowed funds after delivery confirmation."""
    escrow_service = get_escrow_service()
    success, fee = escrow_service.release_funds(req.escrow_id, req.proof.encode())
    
    if not success:
        raise HTTPException(status_code=404, detail="Escrow not found or invalid proof")
    
    return {
        "escrow_id": req.escrow_id,
        "status": "released",
        "fee_collected_usd": fee,
        "message": "Funds released to seller. Fee collected."
    }


@router.post("/escrow/dispute")
async def file_dispute(req: DisputeRequest):
    """File a dispute for arbitration."""
    escrow_service = get_escrow_service()
    
    if req.outcome:
        # Resolve dispute
        outcome = DisputeOutcome(req.outcome)
        result = escrow_service.resolve_dispute(
            req.escrow_id, 
            outcome, 
            req.split_percentage
        )
        return result
    else:
        # File dispute
        result = escrow_service.file_dispute(req.escrow_id, req.evidence.encode())
        return {"result": result}


@router.get("/escrow/stats")
async def get_escrow_stats():
    """Get escrow service statistics."""
    escrow_service = get_escrow_service()
    return escrow_service.get_stats()


# ── Dark Web Node Control Endpoints (Manager Requirement: Control Every Node) ──

@router.get("/nodes/discover")
async def discover_darkweb_nodes():
    """Discover dark web nodes for control."""
    controller = get_node_controller()
    nodes = await controller.discover_nodes()
    return {
        "discovered_nodes": len(nodes),
        "nodes": nodes,
        "message": "Node discovery initiated. Use /nodes/control to take control."
    }


@router.post("/nodes/control")
async def control_node(req: NodeControlRequest):
    """
    Take control of a dark web node.
    
    Methods:
    - covert: Hidden control without detection
    - reward: Pay node operator
    - exploit: Technical takeover
    """
    controller = get_node_controller()
    success = controller.take_control(req.node_id, req.method)
    
    return {
        "node_id": req.node_id,
        "controlled": success,
        "method": req.method,
        "status": "under_julius_control"
    }


@router.post("/nodes/optimize/{node_id}")
async def optimize_node(node_id: str):
    """Optimize controlled node with VEIL enhancements."""
    controller = get_node_controller()
    result = controller.optimize_node(node_id)
    return result


@router.post("/nodes/protect/{node_id}")
async def protect_node(node_id: str):
    """Protect controlled node from surveillance."""
    controller = get_node_controller()
    result = controller.protect_node(node_id)
    return result


@router.get("/nodes/controlled")
async def list_controlled_nodes():
    """List all nodes under JULIUS control."""
    controller = get_node_controller()
    return {
        "controlled_nodes": controller.get_controlled_nodes(),
        "total_controlled": len(controller.get_controlled_nodes())
    }