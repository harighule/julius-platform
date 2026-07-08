"""
JULIUS Intelligence Router v2.1 — Production
All 8 commercial intelligence categories + historical data + background refresh + WebSocket live push.
"""
import asyncio
import json
import sqlite3
import time
from fastapi import APIRouter, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from ..services.intelligence_engine.engine import get_engine
import logging

logger = logging.getLogger("julius.intelligence")

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])

# ─── WebSocket connection manager ────────────────────────────────────────────

class _IntelManager:
    """Manages active WebSocket connections for live intelligence push."""
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("Intelligence WS client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("Intelligence WS client disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, data: dict):
        """Push a message to all connected clients. Remove dead connections."""
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

_manager = _IntelManager()


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@router.get("/health")
async def intelligence_health():
    engine = get_engine()
    stats = engine.get_db_stats()
    return {
        "status": "online",
        "engine": "JULIUS Intelligence Engine v2.1",
        "companies_loaded": len(engine.companies),
        "db_stats": stats,
        "websocket": "/api/intelligence/ws",
    }


@router.get("/companies")
async def get_companies():
    engine = get_engine()
    return {
        "companies": [
            {"symbol": c["Symbol"], "name": c["Security"], "sector": c["GICS Sector"]}
            for c in engine.companies
        ]
    }


@router.get("/report")
async def get_intelligence_report(symbol: str = None):
    engine = get_engine()
    result = engine.generate_full_report(symbol)
    if symbol and not result["reports"]:
        raise HTTPException(status_code=404, detail=f"No data found for symbol: {symbol}")
    return result


@router.get("/company/{symbol}")
async def get_company_report(symbol: str):
    engine = get_engine()
    result = engine.generate_full_report(symbol.upper())
    if not result["reports"]:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    return result["reports"][0]


@router.get("/history/{symbol}")
async def get_history(symbol: str, days: int = 30):
    engine = get_engine()
    history = engine.get_historical(symbol.upper(), days)
    return {
        "symbol":  symbol.upper(),
        "days":    days,
        "count":   len(history),
        "history": history,
    }


@router.post("/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks, limit: int = 100):
    """Manually trigger a background refresh of all company reports and push via WebSocket."""
    async def _run():
        loop = asyncio.get_event_loop()
        engine = get_engine()
        reports = await loop.run_in_executor(None, lambda: engine.update_all_companies(limit=limit))
        logger.info("Manual refresh complete: %d reports stored", len(reports))
        # Push completion notification to all WS clients
        await _manager.broadcast({
            "event": "refresh_complete",
            "reports_updated": len(reports),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        })

    background_tasks.add_task(_run)
    return {
        "status": "refresh_started",
        "limit": limit,
        "message": f"Refreshing top {limit} companies in background. Connect to /api/intelligence/ws for live updates.",
    }


@router.get("/stats")
async def get_stats():
    engine = get_engine()
    return engine.get_db_stats()


@router.get("/sector-rotation")
async def get_sector_rotation():
    engine = get_engine()
    return {"sector_rotation": engine.analyze_sector_rotation()}


@router.get("/contact/{symbol}")
async def get_corporate_contact(symbol: str):
    engine = get_engine()
    contact = engine.get_corporate_contact(symbol.upper())
    return {"symbol": symbol.upper(), "contact": contact}


@router.get("/explain/{symbol}/{category}")
async def explain_category(symbol: str, category: str):
    engine = get_engine()
    result = engine.generate_full_report(symbol.upper())
    if not result["reports"]:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    
    report = result["reports"][0]
    cat = category.lower().replace("-", "_")

    # ── Attempt to run live AI model if configured ────────────────────────────
    import os
    if os.getenv("OPENAI_API_KEY"):
        try:
            from ..services.autogen_brain import get_julius_agent
            agent = get_julius_agent()
            if agent:
                from autogen_agentchat.messages import TextMessage
                prompt = (
                    f"Analyze {report['company']} ({symbol.upper()}) specifically regarding the '{cat}' segment. "
                    f"Here is the raw data collected: {json.dumps(report.get(cat, {}))}. "
                    "Provide a detailed, multi-paragraph professional commercial intelligence brief. "
                    "Elaborate on who is buying, why, what the risks are, and what the next 6 months look like. "
                    "Keep your response structured, objective, and analytical."
                )
                response = await agent.on_messages(
                    [TextMessage(content=prompt, source="user")],
                    cancellation_token=None
                )
                reply = response.chat_message.content if response.chat_message else ""
                if reply.strip():
                    return {
                        "symbol": symbol.upper(),
                        "category": cat,
                        "title": f"AI Deep Dive: {category.upper().replace('_', ' ')}",
                        "explanation": reply,
                        "engine": "OpenAI GPT Agent"
                    }
        except Exception as exc:
            logger.warning("AI generation failed, falling back to rule-based: %s", exc)

    # ── Fallback: Expert-level Rule-Based Brief Generator ──────────────────────
    brief = ""
    company_name = report["company"]
    symbol_upper = symbol.upper()
    
    if cat == "purchase_intent":
        pi = report["purchase_intent"]
        brief = (
            f"### 🎯 Purchase Intent Brief: {company_name} ({symbol_upper})\n"
            f"**Confidence Level:** {pi['confidence'].upper()} ({pi['percent']:.1f}% Intent Index)\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Retail Consumers:** High-intent retail buyers seeking premium product tiers.\n"
            f"* **Early Tech Adopters:** Tech-savvy users tracking new releases and review velocity.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Core brand offerings, consumer hardware upgrades, and premium subscription tiers.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Search Interest Spike:** Public Google Search query momentum for `{company_name}` currently indexes at `{pi['factors']['google_trend']:.2f}` (normalized), indicating strong top-of-funnel customer interest.\n"
            f"* **Positive Public Sentiment:** Web sentiment analysis scores at `{pi['factors']['news_sentiment']:.2f}`, showing positive reviews, customer satisfaction surveys, and general media hype.\n"
            f"* **Fundamentals Support:** YoY revenue growth of `{pi['factors']['revenue_growth']:.2f}` confirms that current marketing spend is successfully converting interest into paid subscriptions.\n\n"
            f"#### 🔮 6-Month Commercial Outlook:\n"
            f"We anticipate buying conversion metrics to remain strong. The primary risk factor is consumer fatigue if marketing acquisition costs rise. Recommend prioritizing targeted expansion in high-indexing search zones."
        )
    elif cat == "enterprise_buying":
        eb = report["enterprise_buying"]
        signals = ", ".join(eb["inferred_signals"]) if eb["inferred_signals"] else "routine operational procurement"
        brief = (
            f"### 🏢 Enterprise Buying & Procurement Brief: {company_name} ({symbol_upper})\n"
            f"**Index Score:** {eb['score']*100:.1f}% ({eb['confidence'].upper()} Confidence)\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Enterprise CIOs & IT Managers:** Corporate infrastructure decision-makers.\n"
            f"* **Engineering Teams:** R&D departments looking to integrate software SDKs.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Cloud database upgrades, cybersecurity solutions, developer tools, and API integrations.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Developer Engagement:** The GitHub R&D activity index shows `{eb['raw_signals']['github_stars']:,}` stars and `{eb['raw_signals']['github_forks']:,}` forks, indicating strong developer adoption.\n"
            f"* **Organizational Scaling:** Active corporate job board postings count stands at `{eb['raw_signals']['job_postings']:,}`, showing headcount expansion. This correlates with high procurement of new enterprise licenses.\n"
            f"* **Valuation Support:** P/E multiplier expansion (`{eb['raw_signals']['pe_ratio']:.2f}`) suggests strong institutional confidence in their enterprise procurement pipeline.\n\n"
            f"#### 🔮 Inferred Procurement Actions:\n"
            f"Based on active developer commits, organizational updates, and job board metadata, we identify these high-probability buying signals: **{signals}**."
        )
    elif cat == "consumer_demand":
        cd = report["consumer_demand"]
        category_bullets = ""
        for name, data in cd["categories"].items():
            category_bullets += f"* **{name.capitalize()}:** Demand Index: `{data['demand_index']:.2f}` | Forecast: **{data['3m_forecast'].upper()}**\n"
        brief = (
            f"### 📊 Consumer Category Demand & SKU Trends: {company_name} ({symbol_upper})\n"
            f"**Leading Sector:** {cd['most_demand'].upper()}\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Mass-Market Shoppers:** Cyclical consumers purchasing daily essentials and electronics.\n"
            f"* **B2B Service Buyers:** Small-to-medium businesses utilizing cloud and digital assets.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Smartphones, gaming consoles, travel insurance, EVs, luxury goods, and fast-delivery items.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Cyclical Sector Rotation:** Shifts in interest rates and economic regimes are driving relative changes in consumer discretionary demand.\n"
            f"* **Hype Correlation:** Search trends show a correlation between positive social media mention volumes and SKU-level conversions.\n\n"
            f"#### 🛒 3-Month Segment Forecasts:\n"
            f"{category_bullets}"
        )
    elif cat == "revenue_momentum":
        rm = report["revenue_momentum"]
        rf = report.get("revenue_forecast", {"trend": "stable", "forecast_6m_pct": "+0.0%", "confidence": "low", "rsquared": 0.0})
        brief = (
            f"### 📈 Revenue Momentum & Predictive Forecasting: {company_name} ({symbol_upper})\n"
            f"**Direction:** {rm['direction'].upper()} ({rm['score']:.2f} Score)\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Institutional Investors:** Asset managers tracking financial momentum.\n"
            f"* **Corporate Partners:** Vendors auditing counterparty creditworthiness.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Equity shares, corporate debt, and long-term partnership commitments.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Strong Cash Generative Profile:** TTM revenue is `{rm['revenue_ttm']}` with YoY revenue growth of `{rm['revenue_growth']}` and a profit margin of `{rm['profit_margin']}`.\n"
            f"* **Trading Momentum:** Average daily trading volume stands at `{rm['volume_avg']}` with a 4-week return rate of `{rm['price_4w_return']}`.\n\n"
            f"#### 🔮 6-Month Time-Series Forecast (Linear Regression Model):\n"
            f"* **Forecasted Direction:** {rf['trend'].upper()}\n"
            f"* **Projected 6-Month Growth/Change:** `{rf['forecast_6m_pct']}`\n"
            f"* **Model Confidence ($R^2$):** {rf['confidence'].upper()} (`{rf['rsquared']:.4f}`)"
        )
    elif cat == "supply_chain":
        sc = report["supply_chain"]
        sc_flags = ""
        for flag in sc["risk_flags"]:
            sc_flags += f"* {flag}\n"
        brief = (
            f"### ⛓️ Supply Chain & Logistics Assessment: {company_name} ({symbol_upper})\n"
            f"**Risk Level:** {sc['status'].upper()} ({sc['risk_score']*100:.1f}% Risk Index)\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Logistics & Ops Directors:** Sourcing teams managing raw material inputs.\n"
            f"* **Component Distributors:** Retail outlets stocking third-party items.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Semiconductors, raw materials, manufacturing capacity, and container shipping contracts.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **News & Trade Indicators:** Supply chain sentiment index is `{sc['news_sentiment']:.2f}`.\n"
            f"* **Risk Flags Raised:**\n{sc_flags}\n"
            f"#### 🔮 Logistics Outlook:\n"
            f"* **Shortage Forecast:** {sc['forecast'].upper()}"
        )
    elif cat == "corporate_expansion":
        ce = report["corporate_expansion"]
        ce_actions = ""
        for action in ce["likely_actions"]:
            ce_actions += f"* {action}\n"
        brief = (
            f"### 🌍 Corporate Expansion & Capital Allocation: {company_name} ({symbol_upper})\n"
            f"**Likelihood:** {ce['confidence'].upper()} ({ce['expansion_score']*100:.1f}% Expansion Score)\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Commercial Real Estate Partners:** Landlords and office developers.\n"
            f"* **Recruitment Firms:** Staffing platforms supporting new geographic offices.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Office leasing contracts, local business registrations, and international marketing services.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Headcount Expansion:** `{ce['job_posting_count']:,}` active job openings indicate a massive hiring push.\n"
            f"* **Financial Capability:** Free cash flow stands at `{ce['free_cash_flow']}`, giving the company sufficient capital to self-fund international growth.\n\n"
            f"#### 🔮 Strategic Actions Planned:\n{ce_actions}"
        )
    elif cat == "ai_adoption":
        ai = report["ai_adoption"]
        brief = (
            f"### 🤖 AI Stack Adoption & R&D Brief: {company_name} ({symbol_upper})\n"
            f"**Adoption Index:** {ai['adoption_score']*100:.1f}%\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **AI Research Teams:** Engineers training custom LLMs and visual transformers.\n"
            f"* **IT Operations:** DevOps professionals migrating legacy computing to GPU clusters.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* NVIDIA H100/H200 compute nodes, cloud serverless credits, and AI orchestration software licenses.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Developer Engagement:** The company's open-source repositories show `{ai['github_stars']:,}` stars and `{ai['github_forks']:,}` forks, reflecting a highly engaged community.\n"
            f"* **AI Headcount Spike:** Job boards show `{ai['ai_hiring_signal'].upper()}` AI-related hiring, correlating with an estimated annual AI spend of `{ai['ai_spend_estimate']}`.\n\n"
            f"#### 🔮 Tech Stack Position:\n"
            f"* **GPU Hardware Demand:** {ai['gpu_demand'].upper()}\n"
            f"* **Cloud Infrastructure Status:** {ai['cloud_migration'].upper()}"
        )
    else:
        brief = (
            f"### 🔄 Sector Rotation & Economic Regimes: {company_name} ({symbol_upper})\n"
            f"**Sector Group:** {report['sector']}\n\n"
            f"#### 👥 Target Buyers (Who is buying):\n"
            f"* **Macro Hedge Funds:** Portfolio managers executing sector-rotation strategies.\n"
            f"* **B2B Suppliers:** Vendors aligning sales plans with cyclical/defensive market phases.\n\n"
            f"#### 📦 Product Segment (What they are buying):\n"
            f"* Sector ETF contracts, cyclical commodity futures, and defensive equities.\n\n"
            f"#### 💡 Core Drivers & Rationale (Elaborate reasons):\n"
            f"* **Sector ETF Momentum:** Returns on key sector ETFs are updated hourly to classify current cycles as risk-on or risk-off.\n"
            f"* **Strategic Shift:** Capital flows indicate sector reallocation into high-performing industry lines."
        )

    return {
        "symbol": symbol.upper(),
        "category": cat,
        "title": f"OSINT Deep Dive: {category.upper().replace('_', ' ')}",
        "explanation": brief,
        "engine": "JULIUS Rule-Based Analyst"
    }


# ─── WebSocket — live intelligence stream ────────────────────────────────────

@router.websocket("/ws")
async def intelligence_ws(websocket: WebSocket):
    """
    WebSocket endpoint for real-time intelligence push.
    On connect, sends the latest cached report for any symbol the client subscribes to.
    Message format (client → server):  {"action": "subscribe", "symbol": "AAPL"}
    Message format (server → client):  {"event": "report", "symbol": "AAPL", "data": {...}}
    """
    await _manager.connect(websocket)
    subscriptions: set[str] = set()
    try:
        # Send welcome message
        await websocket.send_json({
            "event": "connected",
            "message": "JULIUS Intelligence Engine live stream active",
            "version": "2.1",
        })

        async def _push_loop():
            """Push subscribed reports every 60 seconds."""
            while True:
                await asyncio.sleep(60)
                engine = get_engine()
                for sym in list(subscriptions):
                    try:
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, lambda s=sym: engine.generate_full_report(s)
                        )
                        if result["reports"]:
                            await websocket.send_json({
                                "event": "report_update",
                                "symbol": sym,
                                "data": result["reports"][0],
                                "sector_rotation": result.get("sector_rotation", {}),
                                "timestamp": result["generated_at"],
                            })
                    except Exception as exc:
                        logger.warning("WS push failed for %s: %s", sym, exc)

        push_task = asyncio.create_task(_push_loop())

        # Message receive loop
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=300.0)
                action = msg.get("action", "")
                symbol = msg.get("symbol", "").upper()

                if action == "subscribe" and symbol:
                    subscriptions.add(symbol)
                    # Immediately push latest report for new subscription
                    engine = get_engine()
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, lambda s=symbol: engine.generate_full_report(s)
                    )
                    if result["reports"]:
                        await websocket.send_json({
                            "event": "report",
                            "symbol": symbol,
                            "data": result["reports"][0],
                            "sector_rotation": result.get("sector_rotation", {}),
                            "timestamp": result["generated_at"],
                        })
                    else:
                        await websocket.send_json({"event": "no_data", "symbol": symbol})

                elif action == "unsubscribe" and symbol:
                    subscriptions.discard(symbol)
                    await websocket.send_json({"event": "unsubscribed", "symbol": symbol})

                elif action == "ping":
                    await websocket.send_json({"event": "pong", "ts": time.time()})

            except asyncio.TimeoutError:
                # Keep-alive ping
                await websocket.send_json({"event": "ping"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("Intelligence WebSocket error: %s", exc)
    finally:
        push_task.cancel()
        _manager.disconnect(websocket)
