"""
JULIUS — Monero Integration Client
Connects to the public RINO stagenet daemon for privacy-preserving payments.

Phase 1: Daemon connection & info retrieval
"""

from __future__ import annotations

import sys
from typing import Any


def _safe_print(text: str) -> None:
    """Print text in a way that survives Windows cp1252 terminals."""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fall back to writing UTF-8 bytes directly, or strip non-ASCII
        try:
            sys.stdout.buffer.write((text + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
        except AttributeError:
            print(text.encode("ascii", errors="replace").decode())

# Lazy import so the rest of JULIUS still loads if monero-python is absent
try:
    from monero.daemon import Daemon  # type: ignore
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "monero-python is not installed. Run: pip install monero-python"
    ) from _exc

# ── Configuration pulled from central config ──────────────────────────────────
try:
    from backend.config import (  # type: ignore
        MONERO_STAGENET_HOST,
        MONERO_STAGENET_PORT,
        MONERO_ENABLED,
    )
except ImportError:
    # Fallback defaults when running the module standalone.
    # Uses ditatompel's public stagenet node as a well-known alternative;
    # override via MONERO_STAGENET_HOST env-var for RINO or any other node.
    MONERO_STAGENET_HOST = "stagenet.xmr.ditatompel.com"
    MONERO_STAGENET_PORT = 38081
    MONERO_ENABLED = True


# ── Public API ────────────────────────────────────────────────────────────────

def get_monero_daemon() -> Daemon:
    """
    Return a ``Daemon`` instance connected to the public RINO stagenet node.

    Connection parameters are resolved from ``backend.config``
    (``MONERO_STAGENET_HOST`` / ``MONERO_STAGENET_PORT``) and can be
    overridden via environment variables without touching source code.

    Returns
    -------
    monero.daemon.Daemon
        A ready-to-query daemon handle (no persistent socket is kept open;
        each RPC call opens a fresh HTTP connection).
    """
    return Daemon(
        host=MONERO_STAGENET_HOST,
        port=MONERO_STAGENET_PORT,
        timeout=30,
    )


def test_connection() -> Any:
    """
    Connect to the stagenet daemon, print a status summary, and return the
    raw info dict so callers can assert on individual fields.

    Returns
    -------
    dict
        The raw response from ``daemon.info()``.

    Raises
    ------
    ConnectionError
        If the daemon is unreachable or returns an unexpected response.
    """
    daemon = get_monero_daemon()

    try:
        info = daemon.info()
    except Exception as exc:
        raise ConnectionError(
            f"Failed to reach Monero stagenet daemon at "
            f"{MONERO_STAGENET_HOST}:{MONERO_STAGENET_PORT} — {exc}"
        ) from exc

    # ── Pretty-print the key fields ───────────────────────────────────────────
    # monero 1.1.1 returns a NamespacedDict — supports both attribute and key access
    if hasattr(info, "height"):
        height = info.height
        network = getattr(info, "nettype", "unknown")
        top_hash = getattr(info, "top_block_hash", "unknown")
    else:
        height = info.get("height", "unknown")
        network = info.get("nettype", info.get("network_type", "unknown"))
        top_hash = info.get("top_block_hash", "unknown")

    _safe_print("\u2705 Connected to stagenet")
    _safe_print(f"   Height:         {height}")
    _safe_print(f"   Network:        {network}")
    _safe_print(f"   Top block hash: {top_hash}")

    return info


# ── CLI entry-point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        test_connection()
    except (ConnectionError, ImportError) as exc:
        _safe_print(f"\u274c {exc}")
        sys.exit(1)
