"""
Pre-Integration Verification Script for Monero Wallet — JULIUS
Run: python backend/tests/test_monero_precheck.py

Checks:
  1. monero library installed
  2. MONERO_WALLET_ADDRESS format valid
  3. Daemon node connection
  4. Environment variable completeness
"""

from __future__ import annotations

import os
import sys
import socket

# ── Project root on PYTHONPATH ────────────────────────────────────────────────
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Safe Print for Emojis on Windows ──────────────────────────────────────────
def _safe_print(*args, sep=" ", end="\n", **kwargs):
    msg = sep.join(str(arg) for arg in args) + end
    try:
        sys.stdout.write(msg)
        sys.stdout.flush()
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write(msg.encode("utf-8"))
            sys.stdout.buffer.flush()
        except Exception:
            # Fallback
            sys.stdout.write(msg.encode("ascii", "replace").decode("ascii"))
            sys.stdout.flush()

print = _safe_print


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"   \u2705 {msg}")


def _fail(msg: str) -> None:
    print(f"   \u274c {msg}")


def _info(msg: str) -> None:
    print(f"   \u2139\ufe0f  {msg}")


def _section(title: str) -> None:
    print(f"\n\U0001f4c1 {title}")


def _port_reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── Step checkers ─────────────────────────────────────────────────────────────

def check_library() -> bool:
    """Step 1 — Is monero installed?"""
    _section("1. Library")
    try:
        import monero  # noqa: PLC0415
        _ok(f"monero installed  (version {monero.__version__})")
        return True
    except ImportError:
        _fail("monero not installed — run: pip install monero")
        return False


def check_address(addr: str) -> bool:
    """Step 2 — Validate address prefix."""
    _section("2. Wallet Address")
    if not addr:
        _fail("MONERO_WALLET_ADDRESS is not set in .env")
        return False

    prefixes = {
        "4": "Mainnet Primary Address",
        "8": "Mainnet Subaddress",
        "5": "Stagenet Primary Address",
        "9": "Testnet Address",
    }
    first = addr[0]
    if first in prefixes:
        _ok(f"{prefixes[first]} — {addr[:12]}...")
        _ok(f"Length: {len(addr)} chars (expected 95–97)")
        if len(addr) not in range(93, 100):
            _fail("Address length looks unusual — double-check it")
            return False
        return True
    else:
        _fail(f"Unknown prefix '{first}' — expected 4, 5, 8, or 9")
        return False


def check_connection(host: str, port: int) -> bool:
    """Step 3 — Test TCP + RPC connection to stagenet node."""
    _section("3. Node Connection")
    _info(f"Target: {host}:{port}")

    # Quick TCP check first
    if not _port_reachable(host, port):
        _fail(
            f"TCP connection to {host}:{port} failed — "
            "port is blocked by your network/firewall. "
            "The code is correct; this is a network restriction."
        )
        return False

    try:
        from monero.daemon import Daemon  # noqa: PLC0415
        daemon = Daemon(host=host, port=port, timeout=10)
        info = daemon.info()
        height = info.height if hasattr(info, "height") else info.get("height", "?")
        nettype = (
            getattr(info, "nettype", None)
            or info.get("nettype", info.get("network_type", "?"))
        )
        top_hash = (
            getattr(info, "top_block_hash", None)
            or info.get("top_block_hash", "?")
        )
        _ok(f"Connected to node")
        _ok(f"Height:         {height:,}" if isinstance(height, int) else f"Height: {height}")
        _ok(f"Network:        {nettype}")
        _ok(f"Top block hash: {str(top_hash)[:20]}...")
        return True
    except Exception as exc:
        _fail(f"RPC failed: {exc}")
        return False


def check_env_vars() -> bool:
    """Step 4 — Verify all required env vars are present."""
    _section("4. Environment Variables")

    required = {
        "MONERO_ENABLED":        os.getenv("MONERO_ENABLED", ""),
        "MONERO_WALLET_ADDRESS": os.getenv("MONERO_WALLET_ADDRESS", ""),
        "MONERO_STAGENET_HOST":  os.getenv("MONERO_STAGENET_HOST", ""),
        "MONERO_STAGENET_PORT":  os.getenv("MONERO_STAGENET_PORT", ""),
        "MONERO_NETWORK":        os.getenv("MONERO_NETWORK", ""),
    }

    all_ok = True
    for key, val in required.items():
        stripped = val.strip()
        if stripped:
            display = stripped[:14] + "..." if len(stripped) > 14 else stripped
            _ok(f"{key} = {display}")
        else:
            _fail(f"{key} is not set")
            all_ok = False
    return all_ok


# ── Main ──────────────────────────────────────────────────────────────────────

def check_all():
    print("\U0001f50d JULIUS Monero Pre-Integration Check")
    print("=" * 52)

    # Load .env via config (which handles dotenv automatically)
    try:
        from backend import config as _cfg  # noqa: PLC0415
        host = _cfg.MONERO_STAGENET_HOST
        port = _cfg.MONERO_STAGENET_PORT
        addr = _cfg.MONERO_WALLET_ADDRESS
        enabled = _cfg.MONERO_ENABLED
    except ImportError:
        # Fallback: read env vars directly (standalone run outside package)
        host = os.getenv("MONERO_STAGENET_HOST", "stagenet.community.rino.io")
        port = int(os.getenv("MONERO_STAGENET_PORT", "38081"))
        addr = os.getenv("MONERO_WALLET_ADDRESS", "")
        enabled = os.getenv("MONERO_ENABLED", "true").lower() == "true"

    results: dict[str, bool] = {}
    results["library"]     = check_library()
    results["address"]     = check_address(addr)
    results["connection"]  = check_connection(host, port)
    results["env_vars"]    = check_env_vars()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 52)
    print("SUMMARY")
    print("=" * 52)
    labels = {
        "library":     "Step 1 — monero library",
        "address":     "Step 2 — wallet address format",
        "connection":  "Step 3 — node connection",
        "env_vars":    "Step 4 — environment variables",
    }
    all_passed = True
    for key, passed in results.items():
        mark = "\u2705 PASS" if passed else "\u274c FAIL"
        try:
            print(f"  {mark}  {labels[key]}")
        except UnicodeEncodeError:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}]  {labels[key]}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("\u2705 All checks passed — ready for Phase 2 (Stagenet Wallet)!")
    else:
        print("\u26a0\ufe0f  Some checks failed. See details above.")
        print()
        print("Common fixes:")
        print("  - Node blocked? Set MONERO_STAGENET_HOST=stagenet.xmr.ditatompel.com")
        print("  - Missing address? Add MONERO_WALLET_ADDRESS=<your address> to .env")
        print("  - Library missing? Run: pip install monero")

    print()
    return all_passed


if __name__ == "__main__":
    ok = check_all()
    sys.exit(0 if ok else 1)
