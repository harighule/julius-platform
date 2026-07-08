"""
JULIUS Intelligence Engine — Extended Data Sources
Integrates: FRED, NewsAPI, GDELT, SEC EDGAR, BLS, World Bank Data360, GitHub (authenticated)
All calls are cached with TTL. All failures degrade gracefully.
"""

import os
import time
import logging
import requests
import json
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger("julius.data_sources")
_sentiment_analyzer = SentimentIntensityAnalyzer()

# ─── Load API keys from environment ────────────────────────────────────────
FRED_API_KEY    = os.getenv("FRED_API_KEY", "")
NEWS_API_KEY    = os.getenv("NEWS_API_KEY", "")
GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
BLS_API_KEY     = os.getenv("BLS_API_KEY", "")

# World Bank Data360 and GDELT need no keys
WORLDBANK_DATA360_BASE = "https://data360api.worldbank.org"
WORLDBANK_API_BASE     = "https://api.worldbank.org/v2"
GDELT_BASE             = "https://api.gdeltproject.org/api/v2/doc/doc"
SEC_EDGAR_BASE         = "https://efts.sec.gov/LATEST/search-index"
BLS_BASE               = "https://api.bls.gov/publicAPI/v2"
FRED_BASE              = "https://api.stlouisfed.org/fred"
NEWSAPI_BASE           = "https://newsapi.org/v2"

_cache: dict = {}
_cache_time: dict = {}


def _cached_get(key: str, ttl: int, fetcher):
    """Simple TTL cache wrapper."""
    now = time.time()
    if key in _cache and (now - _cache_time.get(key, 0)) < ttl:
        return _cache[key]
    try:
        result = fetcher()
        _cache[key] = result
        _cache_time[key] = now
        return result
    except Exception as exc:
        logger.warning("Data source fetch failed [%s]: %s", key, exc)
        return _cache.get(key)  # stale on failure


# ────────────────────────────────────────────────────────────────────────────
# 1. FRED API — Macroeconomic Indicators
# ────────────────────────────────────────────────────────────────────────────

FRED_SERIES = {
    "cpi":              "CPIAUCSL",     # Consumer Price Index (inflation)
    "fed_funds_rate":   "FEDFUNDS",     # Federal Funds Rate
    "unemployment":     "UNRATE",       # Unemployment Rate
    "gdp_growth":       "A191RL1Q225SBEA",  # Real GDP Growth Rate
    "consumer_confidence": "UMCSENT",   # Michigan Consumer Sentiment
    "retail_sales":     "RSAFS",        # Retail & Food Services Sales
    "industrial_prod":  "INDPRO",       # Industrial Production Index
    "housing_starts":   "HOUST",        # Housing Starts
    "m2_money_supply":  "M2SL",         # M2 Money Supply
    "10yr_yield":       "DGS10",        # 10-Year Treasury Yield
}


def get_fred_indicator(series_id: str, observations: int = 3) -> dict:
    """
    Fetch latest values for a FRED series.
    Returns dict with latest value, previous value, and % change.
    """
    def fetcher():
        url = f"{FRED_BASE}/series/observations"
        params = {
            "series_id":    series_id,
            "api_key":      FRED_API_KEY,
            "file_type":    "json",
            "sort_order":   "desc",
            "limit":        observations,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        obs = [o for o in data.get("observations", []) if o.get("value") != "."]
        if not obs:
            return {"value": None, "previous": None, "change_pct": None}
        latest = float(obs[0]["value"])
        previous = float(obs[1]["value"]) if len(obs) > 1 else latest
        change_pct = ((latest - previous) / abs(previous) * 100) if previous else 0.0
        return {
            "series_id":   series_id,
            "latest":      round(latest, 4),
            "previous":    round(previous, 4),
            "change_pct":  round(change_pct, 2),
            "date":        obs[0]["date"],
        }

    return _cached_get(f"fred_{series_id}", 3600, fetcher) or {}


def get_fred_macro_context() -> dict:
    """
    Fetch a full macro dashboard: inflation, rates, unemployment, GDP, consumer confidence.
    Used to enrich purchase intent and sector rotation signals.
    """
    result = {}
    for name, series_id in FRED_SERIES.items():
        data = get_fred_indicator(series_id)
        if data and data.get("latest") is not None:
            result[name] = data
    return result


def get_fred_demand_signal() -> float:
    """
    Synthesize a single demand signal [0, 1] from FRED macro data.
    High consumer confidence + low unemployment + positive retail sales = high demand.
    """
    try:
        confidence = get_fred_indicator(FRED_SERIES["consumer_confidence"])
        unemployment = get_fred_indicator(FRED_SERIES["unemployment"])
        retail = get_fred_indicator(FRED_SERIES["retail_sales"])

        conf_val = confidence.get("latest", 70.0) / 100.0  # normalize ~0-1
        unemp_val = max(0.0, 1.0 - (unemployment.get("latest", 4.0) / 10.0))  # invert
        retail_chg = min(1.0, max(0.0, 0.5 + retail.get("change_pct", 0.0) / 10.0))

        score = 0.40 * conf_val + 0.35 * unemp_val + 0.25 * retail_chg
        return round(float(score), 4)
    except Exception:
        return 0.5


# ────────────────────────────────────────────────────────────────────────────
# 2. NewsAPI — Real news with API key (100 req/day, cached aggressively)
# ────────────────────────────────────────────────────────────────────────────

def get_newsapi_sentiment(query: str, days: int = 7) -> dict:
    """
    Fetch top headlines from NewsAPI for a query and compute sentiment.
    Returns {sentiment, article_count, top_headlines}.
    24h cache to preserve the 100/day quota.
    """
    def fetcher():
        from datetime import datetime, timedelta
        from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        url = f"{NEWSAPI_BASE}/everything"
        params = {
            "q":        query,
            "from":     from_date,
            "sortBy":   "relevancy",
            "language": "en",
            "pageSize": 20,
            "apiKey":   NEWS_API_KEY,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])

        scores = []
        headlines = []
        for a in articles[:15]:
            text = f"{a.get('title', '')} {a.get('description', '')}"
            if text.strip():
                scores.append(_sentiment_analyzer.polarity_scores(text)["compound"])
                headlines.append(a.get("title", ""))

        avg_sentiment = round(sum(scores) / len(scores), 4) if scores else 0.0
        return {
            "sentiment":      avg_sentiment,
            "article_count":  len(articles),
            "top_headlines":  headlines[:5],
            "source":         "newsapi",
        }

    return _cached_get(f"newsapi_{query[:40]}", 86400, fetcher) or {
        "sentiment": 0.0, "article_count": 0, "top_headlines": [], "source": "newsapi_failed"
    }


# ────────────────────────────────────────────────────────────────────────────
# 3. GDELT — Geopolitical event signals (no key, no rate limit)
# ────────────────────────────────────────────────────────────────────────────

def get_gdelt_signals(query: str, days: int = 7) -> dict:
    """
    Query GDELT Document API for geopolitical/event signals about a company or topic.
    Returns tone (negative = crisis), article volume, and top themes.
    No API key needed. No rate limit beyond fair use.
    """
    def fetcher():
        params = {
            "query":        query,
            "mode":         "artlist",
            "maxrecords":   25,
            "timespan":     f"{days}d",
            "format":       "json",
            "sort":         "DateDesc",
        }
        resp = requests.get(GDELT_BASE, params=params, timeout=12)
        resp.raise_for_status()
        data = resp.json()
        articles = data.get("articles", [])

        tones = []
        headlines = []
        themes = {}
        for a in articles:
            tone_str = a.get("tone", "")
            if tone_str:
                try:
                    tone_val = float(tone_str.split(",")[0])
                    tones.append(tone_val)
                except Exception:
                    pass
            title = a.get("title", "")
            if title:
                headlines.append(title)
            # Collect themes
            for theme in a.get("themes", "").split(";"):
                t = theme.strip()
                if t:
                    themes[t] = themes.get(t, 0) + 1

        avg_tone = round(sum(tones) / len(tones), 2) if tones else 0.0
        # GDELT tone: positive = positive coverage, negative = negative/crisis
        # Normalize to [-1, 1] (GDELT range is typically -100 to +100)
        norm_tone = round(max(-1.0, min(1.0, avg_tone / 10.0)), 4)
        top_themes = sorted(themes.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "tone":           norm_tone,
            "article_count":  len(articles),
            "top_themes":     [t[0] for t in top_themes],
            "top_headlines":  headlines[:3],
            "source":         "gdelt",
        }

    return _cached_get(f"gdelt_{query[:40]}", 3600, fetcher) or {
        "tone": 0.0, "article_count": 0, "top_themes": [], "top_headlines": [], "source": "gdelt_failed"
    }


# ────────────────────────────────────────────────────────────────────────────
# 4. SEC EDGAR Full-Text Search — Enterprise buying signal detection
# ────────────────────────────────────────────────────────────────────────────

SEC_BUYING_KEYWORDS = {
    "cloud_migration":    ["cloud migration", "AWS", "Azure", "Google Cloud", "cloud infrastructure"],
    "erp_replacement":    ["ERP replacement", "SAP implementation", "Oracle ERP", "enterprise software"],
    "cybersecurity":      ["cybersecurity", "zero trust", "SOC 2", "threat detection", "CISO"],
    "ai_adoption":        ["artificial intelligence", "machine learning", "AI deployment", "generative AI"],
    "capex_expansion":    ["capital expenditure", "capacity expansion", "new facility", "manufacturing expansion"],
    "m_and_a":            ["acquisition", "merger", "strategic investment", "joint venture"],
}


def get_sec_edgar_signals(company: str) -> dict:
    """
    Search SEC EDGAR full-text search for enterprise buying signals in 10-K and 8-K filings.
    Returns detected signals and their filing evidence.
    No API key needed.
    """
    def fetcher():
        detected = {}
        for signal_name, keywords in SEC_BUYING_KEYWORDS.items():
            for kw in keywords[:2]:  # limit to first 2 keywords per category to save requests
                try:
                    params = {
                        "q":        f'"{company}" "{kw}"',
                        "forms":    "10-K,8-K",
                        "dateRange": "custom",
                        "startdt":  "2023-01-01",
                    }
                    resp = requests.get(SEC_EDGAR_BASE, params=params, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        hits = data.get("hits", {}).get("total", {}).get("value", 0)
                        if hits > 0:
                            if signal_name not in detected:
                                detected[signal_name] = {"keyword": kw, "filing_count": hits}
                except Exception:
                    pass
        return {
            "detected_signals": detected,
            "signal_count":     len(detected),
            "source":           "sec_edgar",
        }

    return _cached_get(f"sec_{company[:30]}", 86400, fetcher) or {
        "detected_signals": {}, "signal_count": 0, "source": "sec_edgar_failed"
    }


# ────────────────────────────────────────────────────────────────────────────
# 5. BLS API — US Labor Statistics (sector hiring trends, wage growth)
# ────────────────────────────────────────────────────────────────────────────

# Key BLS series for sector rotation and purchase intent signals
BLS_SERIES = {
    "total_nonfarm_jobs":    "CES0000000001",   # Total Nonfarm Payrolls
    "tech_jobs":             "CES5051000001",   # Information sector employment
    "manufacturing_jobs":    "CES3000000001",   # Manufacturing employment
    "retail_jobs":           "CES4200000001",   # Retail employment
    "healthcare_jobs":       "CES6562000001",   # Healthcare employment
    "avg_hourly_earnings":   "CES0000000003",   # Average Hourly Earnings
}


def get_bls_employment(series_ids: list = None) -> dict:
    """
    Fetch latest employment statistics from BLS for multiple series.
    Returns dict with series_id -> {value, change, date}.
    """
    if series_ids is None:
        series_ids = list(BLS_SERIES.values())

    def fetcher():
        url = f"{BLS_BASE}/timeseries/data/"
        payload = {
            "seriesid":    series_ids,
            "registrationkey": BLS_API_KEY,
            "startyear":   "2023",
            "endyear":     "2025",
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = {}
        reverse_lookup = {v: k for k, v in BLS_SERIES.items()}
        for series in data.get("Results", {}).get("series", []):
            sid = series["seriesID"]
            sdata = series.get("data", [])
            if sdata:
                latest = sdata[0]
                previous = sdata[1] if len(sdata) > 1 else latest
                latest_val = float(latest.get("value", 0))
                prev_val = float(previous.get("value", latest_val))
                chg = ((latest_val - prev_val) / abs(prev_val) * 100) if prev_val else 0.0
                name = reverse_lookup.get(sid, sid)
                result[name] = {
                    "value":      round(latest_val, 2),
                    "change_pct": round(chg, 2),
                    "period":     f"{latest.get('year')}-{latest.get('period')}",
                }
        return result

    return _cached_get("bls_employment", 86400, fetcher) or {}


def get_bls_sector_signal() -> dict:
    """
    Derive sector hiring momentum scores from BLS data.
    Returns dict of sector -> momentum [0, 1].
    """
    try:
        data = get_bls_employment()
        signals = {}

        # Tech sector
        if "tech_jobs" in data:
            chg = data["tech_jobs"].get("change_pct", 0)
            signals["technology"] = round(0.5 + min(0.5, max(-0.5, chg / 5)), 4)

        # Manufacturing
        if "manufacturing_jobs" in data:
            chg = data["manufacturing_jobs"].get("change_pct", 0)
            signals["industrials"] = round(0.5 + min(0.5, max(-0.5, chg / 5)), 4)

        # Retail
        if "retail_jobs" in data:
            chg = data["retail_jobs"].get("change_pct", 0)
            signals["consumer_discretionary"] = round(0.5 + min(0.5, max(-0.5, chg / 5)), 4)

        # Healthcare
        if "healthcare_jobs" in data:
            chg = data["healthcare_jobs"].get("change_pct", 0)
            signals["healthcare"] = round(0.5 + min(0.5, max(-0.5, chg / 5)), 4)

        return signals
    except Exception:
        return {}


# ────────────────────────────────────────────────────────────────────────────
# 6. World Bank Data360 API — Country-level demand baselines
# ────────────────────────────────────────────────────────────────────────────

# Useful indicator IDs from World Bank WDI
WORLDBANK_INDICATORS = {
    "gdp_per_capita":   "WB_WDI_NY_GDP_PCAP_CD",         # GDP per capita (USD)
    "gni_per_capita":   "WB_WDI_NY_GNP_PCAP_CD",         # GNI per capita
    "consumer_expend":  "WB_WDI_NE_CON_PRVT_PP_KD",      # Household final consumption
    "internet_users":   "WB_WDI_IT_NET_USER_ZS",         # Internet users % of population
    "mobile_subs":      "WB_WDI_IT_CEL_SETS_P2",         # Mobile subscriptions per 100
    "inflation":        "WB_WDI_FP_CPI_TOTL_ZG",         # Inflation, consumer prices (annual %)
    "trade_openness":   "WB_WDI_NE_TRD_GNFS_ZS",         # Trade as % of GDP
}

COUNTRY_CODES = {
    "United States":  "USA",
    "China":          "CHN",
    "Germany":        "DEU",
    "India":          "IND",
    "Japan":          "JPN",
    "United Kingdom": "GBR",
    "Brazil":         "BRA",
    "France":         "FRA",
}


def get_worldbank_country_data(country_code: str = "USA", indicator_id: str = "WB_WDI_NY_GDP_PCAP_CD") -> dict:
    """
    Fetch a single World Bank Data360 indicator for a country.
    Returns the latest observation value and time period.
    No API key required.
    """
    def fetcher():
        params = {
            "DATABASE_ID": "WB_WDI",
            "INDICATOR":   indicator_id,
            "REF_AREA":    country_code,
            "timePeriodFrom": "2020",
            "skip":        0,
        }
        resp = requests.get(
            f"{WORLDBANK_DATA360_BASE}/data360/data",
            params=params,
            timeout=12
        )
        resp.raise_for_status()
        data = resp.json()
        values = data.get("value", [])
        # Filter to latest data only
        latest_vals = [v for v in values if v.get("LATEST_DATA") is True]
        if not latest_vals:
            latest_vals = sorted(values, key=lambda x: x.get("TIME_PERIOD", ""), reverse=True)

        if latest_vals:
            v = latest_vals[0]
            return {
                "value":       v.get("OBS_VALUE"),
                "time_period": v.get("TIME_PERIOD"),
                "indicator":   v.get("COMMENT_TS", indicator_id),
                "country":     country_code,
                "source":      "worldbank_data360",
            }
        return {"value": None, "country": country_code, "source": "worldbank_data360_empty"}

    return _cached_get(f"wb_{country_code}_{indicator_id[-10:]}", 86400, fetcher) or {}


def get_worldbank_demand_index(country_code: str = "USA") -> float:
    """
    Derive a consumer demand index [0, 1] from World Bank indicators.
    Combines GDP per capita, consumer expenditure, and internet users.
    """
    try:
        gdp = get_worldbank_country_data(country_code, WORLDBANK_INDICATORS["gdp_per_capita"])
        internet = get_worldbank_country_data(country_code, WORLDBANK_INDICATORS["internet_users"])
        inflation_data = get_worldbank_country_data(country_code, WORLDBANK_INDICATORS["inflation"])

        # GDP per capita: normalize to [0, 1] where $80k+ = 1.0
        gdp_val = float(gdp.get("value") or 40000)
        gdp_score = min(1.0, gdp_val / 80000)

        # Internet penetration: direct percentage [0-100] -> [0, 1]
        internet_val = float(internet.get("value") or 70)
        internet_score = min(1.0, internet_val / 100)

        # Inflation: low inflation = better demand. >10% = bad.
        inflation_val = float(inflation_data.get("value") or 3)
        inflation_score = max(0.0, 1.0 - (abs(inflation_val) / 10))

        return round(0.40 * gdp_score + 0.35 * internet_score + 0.25 * inflation_score, 4)
    except Exception:
        return 0.5


# ────────────────────────────────────────────────────────────────────────────
# 7. GitHub (Authenticated) — 5,000 req/hr instead of 60
# ────────────────────────────────────────────────────────────────────────────

def get_github_activity_auth(query: str) -> dict:
    """
    Search GitHub repositories with authentication token for higher rate limits.
    Returns {stars, forks, watchers, open_issues, repo_name, language, updated_at}.
    """
    def fetcher():
        headers = {
            "Accept":        "application/vnd.github+json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        params = {
            "q":       query,
            "sort":    "stars",
            "order":   "desc",
            "per_page": 1,
        }
        resp = requests.get(
            "https://api.github.com/search/repositories",
            headers=headers,
            params=params,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return {"stars": 0, "forks": 0, "watchers": 0, "open_issues": 0}
        top = items[0]
        return {
            "stars":       top.get("stargazers_count", 0),
            "forks":       top.get("forks_count", 0),
            "watchers":    top.get("watchers_count", 0),
            "open_issues": top.get("open_issues_count", 0),
            "repo_name":   top.get("full_name", ""),
            "language":    top.get("language", ""),
            "updated_at":  top.get("updated_at", ""),
        }

    return _cached_get(f"github_auth_{query[:40]}", 3600, fetcher) or {
        "stars": 0, "forks": 0, "watchers": 0, "open_issues": 0
    }


# ────────────────────────────────────────────────────────────────────────────
# Composite signal builder — used by engine.py
# ────────────────────────────────────────────────────────────────────────────

def get_enriched_signals(company_name: str, country_code: str = "USA") -> dict:
    """
    Build a single enriched signal dict from all data sources.
    Called once per report and merged into the intelligence report.
    """
    result = {
        "fred_macro":          get_fred_macro_context(),
        "fred_demand_signal":  get_fred_demand_signal(),
        "newsapi":             get_newsapi_sentiment(company_name),
        "gdelt":               get_gdelt_signals(company_name),
        "sec_edgar":           get_sec_edgar_signals(company_name),
        "bls_sector":          get_bls_sector_signal(),
        "worldbank_demand":    get_worldbank_demand_index(country_code),
    }
    return result
