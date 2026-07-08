"""
JULIUS — Unified Configuration
Centralized settings for the entire JULIUS platform.
"""

import os

# Load .env file if present
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    # python-dotenv not installed — fall back to manual loading
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    from .utils import safe_strip
                    os.environ.setdefault(safe_strip(_k), safe_strip(_v))

# ── Server ─────────────────────────────────────────────────────────────────
HOST = os.getenv("JULIUS_HOST", "0.0.0.0")
PORT = int(os.getenv("JULIUS_PORT", "8000"))
DEBUG = os.getenv("JULIUS_DEBUG", "1") == "1"

# ── Database ───────────────────────────────────────────────────────────────
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.getenv("DB_PATH_OVERRIDE") or os.path.join(DB_DIR, "julius.db")

# ── Auth ───────────────────────────────────────────────────────────────────
# IMPORTANT: Set these via environment variables in production!
# If not set, secure random defaults are generated at startup.
import secrets as _secrets
JWT_SECRET = os.getenv("JWT_SECRET") or _secrets.token_hex(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
ADMIN_DEFAULT_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD") or _secrets.token_urlsafe(12)

# ── Sandbox (File Browser) ─────────────────────────────────────────────────
SANDBOX_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "sandbox"))
os.makedirs(SANDBOX_ROOT, exist_ok=True)

# ── OpenAI (optional for enhanced NLP) ──────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

# ── Event Bus ──────────────────────────────────────────────────────────────
EVENT_BUS_MAX_EVENTS = 500

# ── Network Monitor ────────────────────────────────────────────────────────
MONITOR_USER_MAX_CHECKS = 20
MONITOR_USER_WINDOW = 60
MONITOR_GLOBAL_MAX_CHECKS = 100
MONITOR_GLOBAL_WINDOW = 60

# ── Settings persistence ──────────────────────────────────────────────────
import json as _json
from pathlib import Path as _Path

DATA_DIR = _Path(DB_DIR)
SETTINGS_FILE = DATA_DIR / "settings.json"

_DEFAULT_SETTINGS = {
    "scanner_port_range": "1-1024",
    "scanner_timeout": 5,
    "rate_limit_max": 100,
    "rate_limit_window": 3600,
    "autoscan_enabled": False,
    "autoscan_interval": 3600,
    "ai_model": "gpt-4o-mini",
    "ai_temperature": 0.7,
}

def get_editable_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return _json.loads(SETTINGS_FILE.read_text())
        except Exception:
            pass
    return dict(_DEFAULT_SETTINGS)

def update_settings(data: dict):
    current = get_editable_settings()
    current.update(data)
    SETTINGS_FILE.write_text(_json.dumps(current, indent=2))


# ── Token Issuer (Blind Signature Bandwidth Tokens) ────────────────────────
VEIL_TOKEN_ISSUER_ENABLED = os.getenv("VEIL_TOKEN_ISSUER_ENABLED", "false").lower() == "true"
VEIL_TOKEN_ISSUER_PRIVATE_KEY_FILE = os.getenv(
    "VEIL_TOKEN_ISSUER_PRIVATE_KEY_FILE",
    "data/tokens/issuer_private.pem",
)
VEIL_TOKEN_ISSUER_PUBLIC_KEY_FILE = os.getenv(
    "VEIL_TOKEN_ISSUER_PUBLIC_KEY_FILE",
    "data/tokens/issuer_public.pem",
)
VEIL_TOKEN_VALIDITY_DAYS = int(os.getenv("VEIL_TOKEN_VALIDITY_DAYS", "30"))
VEIL_TOKEN_DEFAULT_DENOMINATION = int(os.getenv("VEIL_TOKEN_DEFAULT_DENOMINATION", "10"))
VEIL_TOKEN_ISSUER_URL = os.getenv("VEIL_TOKEN_ISSUER_URL", "http://localhost:8000/tokens")
VEIL_TOKEN_REQUIRED = os.getenv("VEIL_TOKEN_REQUIRED", "true").lower() == "true"
VEIL_TOKEN_CACHE_TTL = int(os.getenv("VEIL_TOKEN_CACHE_TTL", "300"))  # seconds

# ── Settlement Engine ──────────────────────────────────────────────────────
VEIL_SETTLEMENT_ENABLED = os.getenv("VEIL_SETTLEMENT_ENABLED", "true").lower() == "true"
VEIL_SETTLEMENT_BATCH_INTERVAL = int(os.getenv("VEIL_SETTLEMENT_BATCH_INTERVAL", "3600"))  # seconds
VEIL_SETTLEMENT_COMMISSION_RATE = float(os.getenv("VEIL_SETTLEMENT_COMMISSION_RATE", "0.001"))  # $/MB
VEIL_SETTLEMENT_MIN_PAYOUT = float(os.getenv("VEIL_SETTLEMENT_MIN_PAYOUT", "1.0"))  # dollars

# ── Passive Dark-Web Node Discovery ───────────────────────────────────────
VEIL_DISCOVERY_ENABLED = os.getenv("VEIL_DISCOVERY_ENABLED", "true").lower() == "true"
VEIL_DISCOVERY_INTERVAL = int(os.getenv("VEIL_DISCOVERY_INTERVAL", "86400"))   # 24 hours
VEIL_DISCOVERY_MAX_NODES = int(os.getenv("VEIL_DISCOVERY_MAX_NODES", "1000"))
VEIL_DISCOVERY_SOURCES = os.getenv("VEIL_DISCOVERY_SOURCES", "tor_metrics,i2p_netdb,public_dns")

# ── Referral System ────────────────────────────────────────────────────────
VEIL_REFERRAL_ENABLED = os.getenv("VEIL_REFERRAL_ENABLED", "true").lower() == "true"
VEIL_REFERRAL_BONUS_PERCENT = float(os.getenv("VEIL_REFERRAL_BONUS_PERCENT", "0.05"))  # 5%
VEIL_REFERRAL_MAX_LEVELS = int(os.getenv("VEIL_REFERRAL_MAX_LEVELS", "3"))  # depth of referral tree
VEIL_REFERRAL_COOLDOWN_DAYS = int(os.getenv("VEIL_REFERRAL_COOLDOWN_DAYS", "7"))  # days before referral bonus starts

# ── Partner Onboarding ─────────────────────────────────────────────────────
VEIL_ONBOARDING_ENABLED = os.getenv("VEIL_ONBOARDING_ENABLED", "true").lower() == "true"
VEIL_ONBOARDING_SSH_KEY_FILE = os.getenv(
    "VEIL_ONBOARDING_SSH_KEY_FILE", "data/ssh/onboarding_key"
)
VEIL_ONBOARDING_REVENUE_SHARE_DEFAULT = float(
    os.getenv("VEIL_ONBOARDING_REVENUE_SHARE_DEFAULT", "0.30")
)
VEIL_ONBOARDING_REFERRAL_BONUS = float(
    os.getenv("VEIL_ONBOARDING_REFERRAL_BONUS", "0.05")
)
VEIL_ONBOARDING_MAX_ATTEMPTS = int(os.getenv("VEIL_ONBOARDING_MAX_ATTEMPTS", "3"))
VEIL_ONBOARDING_NETWORK_URL = os.getenv(
    "VEIL_ONBOARDING_NETWORK_URL", "https://onboarding.julius-veil.net"
)

# ── Metrics Collector ──────────────────────────────────────────────────────
VEIL_COLLECTOR_ENABLED = os.getenv("VEIL_COLLECTOR_ENABLED", "true").lower() == "true"
VEIL_COLLECTOR_INTERVAL = int(os.getenv("VEIL_COLLECTOR_INTERVAL", "60"))  # seconds
VEIL_COLLECTOR_HISTORY_RETENTION_DAYS = int(
    os.getenv("VEIL_COLLECTOR_HISTORY_RETENTION_DAYS", "30")
)
VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY = float(
    os.getenv("VEIL_COLLECTOR_ALERT_THRESHOLD_LATENCY", "5.0")  # seconds
)
VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE = int(
    os.getenv("VEIL_COLLECTOR_ALERT_THRESHOLD_QUEUE", "100")
)

# ── AI Network Optimizer ───────────────────────────────────────────────────
VEIL_OPTIMIZER_ENABLED = os.getenv("VEIL_OPTIMIZER_ENABLED", "true").lower() == "true"
VEIL_OPTIMIZER_INTERVAL = int(os.getenv("VEIL_OPTIMIZER_INTERVAL", "300"))  # 5 minutes

# Lambda (Poisson mixing delay) bounds
VEIL_OPTIMIZER_LAMBDA_MIN = float(os.getenv("VEIL_OPTIMIZER_LAMBDA_MIN", "0.05"))
VEIL_OPTIMIZER_LAMBDA_MAX = float(os.getenv("VEIL_OPTIMIZER_LAMBDA_MAX", "0.5"))

# Strata count bounds
VEIL_OPTIMIZER_STRATA_MIN = int(os.getenv("VEIL_OPTIMIZER_STRATA_MIN", "3"))
VEIL_OPTIMIZER_STRATA_MAX = int(os.getenv("VEIL_OPTIMIZER_STRATA_MAX", "5"))

# Cover-traffic ratio bounds (ratio to real traffic)
VEIL_OPTIMIZER_COVER_MIN = float(os.getenv("VEIL_OPTIMIZER_COVER_MIN", "0.5"))
VEIL_OPTIMIZER_COVER_MAX = float(os.getenv("VEIL_OPTIMIZER_COVER_MAX", "2.0"))

# Minimum anonymity set size (active nodes) before strata changes are triggered
VEIL_OPTIMIZER_ANONYMITY_THRESHOLD = int(
    os.getenv("VEIL_OPTIMIZER_ANONYMITY_THRESHOLD", "100")
)

# ── Attack Detector ────────────────────────────────────────────────────────
VEIL_DETECTOR_ENABLED = os.getenv("VEIL_DETECTOR_ENABLED", "true").lower() == "true"
VEIL_DETECTOR_INTERVAL = int(os.getenv("VEIL_DETECTOR_INTERVAL", "120"))  # 2 minutes
VEIL_DETECTOR_TIMING_THRESHOLD = float(os.getenv("VEIL_DETECTOR_TIMING_THRESHOLD", "2.0"))  # std deviations
VEIL_DETECTOR_SYBIL_THRESHOLD = int(os.getenv("VEIL_DETECTOR_SYBIL_THRESHOLD", "5"))  # identical fingerprints
VEIL_DETECTOR_INTERSECTION_THRESHOLD = int(os.getenv("VEIL_DETECTOR_INTERSECTION_THRESHOLD", "10"))  # repeated connections
VEIL_DETECTOR_AUTO_RESPOND = os.getenv("VEIL_DETECTOR_AUTO_RESPOND", "true").lower() == "true"

# ── Monero (XMR) Integration ──────────────────────────────────────────────────────
# Phase 1: Stagenet daemon connection for development & testing.
# Primary node: RINO community stagenet (stagenet.community.rino.io:38081)
# Alternative:  ditatompel public stagenet (stagenet.xmr.ditatompel.com:38081)
# Override via environment variables to switch nodes or move to mainnet.
MONERO_STAGENET_HOST = os.getenv("MONERO_STAGENET_HOST", "stagenet.community.rino.io")
MONERO_STAGENET_PORT = int(os.getenv("MONERO_STAGENET_PORT", "38081"))
MONERO_ENABLED = os.getenv("MONERO_ENABLED", "true").lower() == "true"
MONERO_NETWORK = os.getenv("MONERO_NETWORK", "stagenet")              # stagenet | mainnet | testnet
MONERO_WALLET_ADDRESS = os.getenv("MONERO_WALLET_ADDRESS", "")        # XMR address (set in .env)
MONERO_VIEW_KEY = os.getenv("MONERO_VIEW_KEY", "")                    # Private view key
MONERO_SPEND_KEY = os.getenv("MONERO_SPEND_KEY", "")                  # Private spend key (keep secret on mainnet)
MONERO_WALLET_FILE = os.getenv("MONERO_WALLET_FILE", "")              # Path to wallet binary file
MONERO_WALLET_PASSWORD = os.getenv("MONERO_WALLET_PASSWORD", "")      # Wallet password
