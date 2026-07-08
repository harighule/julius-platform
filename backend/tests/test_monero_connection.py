"""
JULIUS — Monero Stagenet Connection Test
Phase 1: Verify daemon connectivity and basic info retrieval.

Run with:
    python -m pytest backend/tests/test_monero_connection.py -v
or directly:
    python backend/tests/test_monero_connection.py

The live integration test (test_monero_connection_live) is marked with
``pytest.mark.network`` and is automatically skipped when port 38081
is unreachable (e.g. behind a firewall).
The mock-based test (test_monero_connection_mock) always passes.
"""

from __future__ import annotations

import socket
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on PYTHONPATH when running directly
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _port_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    """Return True if we can TCP-connect to host:port within timeout seconds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── Mock-based unit test (always passes, no network needed) ───────────────────────

def test_monero_connection_mock():
    """
    Unit test — patches the daemon so no real network connection is made.
    Verifies the full test_connection() logic including assertions.
    """
    fake_info = MagicMock()
    fake_info.height = 1_654_321
    fake_info.nettype = "stagenet"
    fake_info.top_block_hash = (
        "abc123def456789abcdef0123456789abcdef0123456789abcdef0123456789"
    )

    with patch("monero.daemon.Daemon.info", return_value=fake_info):
        from backend.crypto.monero_client import test_connection  # noqa: PLC0415

        info = test_connection()

    height = info.height if hasattr(info, "height") else info.get("height", 0)
    assert height > 0, (
        f"Blockchain height should be > 0 but got {height!r}. "
        "Check the mock setup."
    )
    print(f"\n[MOCK] Assertion passed — blockchain height is {height:,}")


# ── Live integration test (requires network access to stagenet) ─────────────────

@pytest.mark.network
def test_monero_connection_live():
    """
    Integration test — connects to the actual public RINO stagenet node and
    asserts that the blockchain is synchronised (height > 0).

    Automatically skipped when port 38081 is unreachable.
    """
    from backend.config import MONERO_STAGENET_HOST, MONERO_STAGENET_PORT  # noqa: PLC0415

    if not _port_reachable(MONERO_STAGENET_HOST, MONERO_STAGENET_PORT):
        pytest.skip(
            f"Stagenet node {MONERO_STAGENET_HOST}:{MONERO_STAGENET_PORT} "
            "is not reachable from this network — skipping live test."
        )

    from backend.crypto.monero_client import test_connection  # noqa: PLC0415

    info = test_connection()

    # ── Resolve height regardless of whether info is a dict or object ───────────
    if isinstance(info, dict):
        height = info.get("height", 0)
    else:
        height = getattr(info, "height", 0) or 0

    assert height > 0, (
        f"Blockchain height should be > 0 but got {height!r}. "
        "The daemon may be unreachable or still syncing."
    )

    print(f"\n[LIVE] Assertion passed — blockchain height is {height:,}")


# ── Direct-run entry-point ───────────────────────────────────────────────────
if __name__ == "__main__":
    # Run the mock test
    test_monero_connection_mock()
    print("Mock test passed.")

    # Attempt live test
    from backend.config import MONERO_STAGENET_HOST, MONERO_STAGENET_PORT  # noqa: PLC0415
    if _port_reachable(MONERO_STAGENET_HOST, MONERO_STAGENET_PORT):
        test_monero_connection_live()
        print("Live test passed.")
    else:
        print(
            f"[SKIP] Live test skipped — {MONERO_STAGENET_HOST}:{MONERO_STAGENET_PORT} "
            "not reachable from this network."
        )
