"""
JULIUS — Mix Node Token Integration Tests
Tests that the /mix/process endpoint correctly enforces token verification.

Run with:
    python -m pytest backend/tests/test_mix_node_tokens.py -v
"""

import hashlib
import os
import secrets
import sys
from typing import Set, Tuple, Optional

# ── Path bootstrap ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Set env vars BEFORE any backend module is imported so config picks them up.
os.environ.setdefault("JULIUS_DEBUG", "0")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("ADMIN_DEFAULT_PASSWORD", "TestAdmin@1234")
os.environ.setdefault("DB_PATH_OVERRIDE", ":memory:")
# Token enforcement is ON by default (default "true" in config); force it here
# so the test suite is self-contained even if a .env file overrides it.
os.environ["VEIL_TOKEN_REQUIRED"] = "true"

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from backend.tokens.issuer import TokenIssuer

# ── Wire-format constants (must match issuer.py / token_manager.py) ──────────
_SERIAL_BYTES = 32
_SIG_BYTES    = 256
_TOKEN_BYTES  = _SERIAL_BYTES + _SIG_BYTES   # 288 bytes → 576 hex chars


# ── Fake TokenManager (no HTTP) ───────────────────────────────────────────────

class FakeTokenManager:
    """
    Drop-in replacement for TokenManager used during tests.

    Performs RSA verification locally against an in-memory TokenIssuer so
    no HTTP server is needed.  Tracks spent serials and expired serials in
    plain Python sets.
    """

    def __init__(self, issuer: TokenIssuer) -> None:
        self._issuer = issuer
        self._spent_serials: Set[bytes] = set()   # SHA-256 digests
        self._expired_serials: Set[bytes] = set() # raw serial bytes

        pub_pem = issuer.get_public_key()
        self._public_key_pem: bytes = pub_pem
        self._public_key_obj = serialization.load_pem_public_key(pub_pem)

    # ── Public interface (mirrors TokenManager) ───────────────────────────────

    def get_public_key(self) -> bytes:
        return self._public_key_pem

    def verify_token(self, token: bytes) -> Tuple[bool, str]:
        """
        1. Length check
        2. Expiry check (test-controlled)
        3. RSA signature
        4. Double-spend check
        """
        if len(token) != _TOKEN_BYTES:
            return False, f"invalid token length {len(token)} (expected {_TOKEN_BYTES})"

        serial    = token[:_SERIAL_BYTES]
        sig_bytes = token[_SERIAL_BYTES:]

        # ── Expiry ─────────────────────────────────────────────────────────
        if serial in self._expired_serials:
            return False, "token expired"

        # ── RSA signature ──────────────────────────────────────────────────
        pub_numbers = self._public_key_obj.public_numbers()
        n, e = pub_numbers.n, pub_numbers.e
        serial_int = int.from_bytes(serial, "big")
        sig_int    = int.from_bytes(sig_bytes, "big")

        if pow(sig_int, e, n) != serial_int:
            return False, "RSA signature verification failed"

        # ── Double-spend ───────────────────────────────────────────────────
        serial_hash = hashlib.sha256(serial).digest()
        if serial_hash in self._spent_serials:
            return False, "token already spent (double-spend)"

        self._spent_serials.add(serial_hash)
        return True, "ok"

    def report_usage(self, token_serial: bytes, bytes_used: int) -> bool:  # noqa: D401
        return True  # no-op in tests

    # ── Test helpers ──────────────────────────────────────────────────────────

    def mark_expired(self, serial: bytes) -> None:
        """Mark a serial as expired so the next verify_token call returns 403."""
        self._expired_serials.add(serial)


# ── Module-scoped fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def issuer() -> TokenIssuer:
    """Transient RSA-2048 TokenIssuer for the test session."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return TokenIssuer(private_key_pem=priv_pem)


@pytest.fixture(scope="module")
def fake_tm(issuer: TokenIssuer) -> FakeTokenManager:
    return FakeTokenManager(issuer)


@pytest.fixture(scope="module")
def client(fake_tm: FakeTokenManager) -> TestClient:
    """
    TestClient wired to a minimal FastAPI app that mounts the mix-node router.

    We inject `fake_tm` as the module-level singleton so no HTTP issuer is
    required during tests.
    """
    import backend.veil.mix_node as mix_mod
    mix_mod._token_manager = fake_tm          # inject fake before first request

    from backend.veil.mix_node import router as mix_router
    app = FastAPI(title="MixNodeTestApp")
    app.include_router(mix_router)
    return TestClient(app)


# ── Token creation helper ─────────────────────────────────────────────────────

def make_valid_token(issuer: TokenIssuer) -> Tuple[bytes, str]:
    """
    Simulate the client-side blind-sign-unblind flow.

    Returns
    -------
    (serial_bytes, token_hex)
        serial_bytes — raw 32-byte serial (for ack verification / expiry marking)
        token_hex    — 576-char hex string suitable for ProcessRequest.token
    """
    pub_numbers = issuer._public_key.public_numbers()
    n, e = pub_numbers.n, pub_numbers.e

    # 1. Fresh random serial
    serial = secrets.token_bytes(_SERIAL_BYTES)
    serial_int = int.from_bytes(serial, "big")

    # 2. Random blinding factor
    r = secrets.randbits(2048) % n
    if r == 0:
        r = 1

    # 3. Blind: B = serial_int * r^e mod n
    blinded_int   = (serial_int * pow(r, e, n)) % n
    blinded_bytes = blinded_int.to_bytes(_SIG_BYTES, "big")

    # 4. Issuer blind-signs
    signed_blinded     = issuer.issue_token(blinded_bytes)
    signed_blinded_int = int.from_bytes(signed_blinded, "big")

    # 5. Unblind: sig = signed_blinded * r^{-1} mod n
    r_inv     = pow(r, -1, n)
    sig_int   = (signed_blinded_int * r_inv) % n
    sig_bytes = sig_int.to_bytes(_SIG_BYTES, "big")

    # 6. Compose spendable token
    token = serial + sig_bytes
    assert len(token) == _TOKEN_BYTES
    return serial, token.hex()


# ════════════════════════════════════════════════════════════════════════════
# Test Suite
# ════════════════════════════════════════════════════════════════════════════

class TestMixNodeTokenEnforcement:
    """
    Integration tests: all 4 required scenarios plus 2 bonus cases.
    Each test calls POST /mix/process through the TestClient.
    """

    # ── Test 1: Valid token ───────────────────────────────────────────────────

    def test_valid_token_packet_accepted(self, client: TestClient, issuer: TokenIssuer):
        """
        A correctly signed, unspent token must be accepted (HTTP 200) and the
        packet must be processed (next_hop_packet present).
        """
        _, token_hex = make_valid_token(issuer)
        resp = client.post("/mix/process", json={
            "packet_hex": "deadbeef" * 4,   # 16 bytes
            "token":      token_hex,
            "node_id":    "test-node-valid",
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["status"] == "ok"
        assert body["next_hop_packet"] is not None, "next_hop_packet must not be None"
        assert body["usage_acknowledgment"] is not None, "usage_acknowledgment must be set"

    # ── Test 2: Invalid (bad signature) token ────────────────────────────────

    def test_invalid_token_rejected_with_403(self, client: TestClient):
        """
        A token whose signature is random garbage must be rejected with HTTP 403.
        """
        bad_token = secrets.token_bytes(_TOKEN_BYTES).hex()
        resp = client.post("/mix/process", json={
            "packet_hex": "cafebabe" * 4,
            "token":      bad_token,
            "node_id":    "test-node-invalid",
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        detail = resp.json()["detail"].lower()
        assert "invalid token" in detail, f"Unexpected detail: {detail}"

    # ── Test 3: Expired token ─────────────────────────────────────────────────

    def test_expired_token_rejected_with_403(
        self,
        client: TestClient,
        issuer: TokenIssuer,
        fake_tm: FakeTokenManager,
    ):
        """
        A token whose serial has been flagged as expired must be rejected with
        HTTP 403 and the detail must mention 'expired'.
        """
        serial, token_hex = make_valid_token(issuer)
        fake_tm.mark_expired(serial)   # simulate TTL expiry

        resp = client.post("/mix/process", json={
            "packet_hex": "aabbccdd" * 4,
            "token":      token_hex,
            "node_id":    "test-node-expired",
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        detail = resp.json()["detail"].lower()
        assert "expired" in detail, f"Unexpected detail: {detail}"

    # ── Test 4: Double-spent token ────────────────────────────────────────────

    def test_double_spent_token_rejected_with_403(
        self,
        client: TestClient,
        issuer: TokenIssuer,
    ):
        """
        The first use of a token must succeed (HTTP 200).
        The second use of the same token must be rejected (HTTP 403) as a
        double-spend attempt.
        """
        _, token_hex = make_valid_token(issuer)
        payload = {
            "packet_hex": "11223344" * 4,
            "token":      token_hex,
            "node_id":    "test-node-doublespend",
        }

        # First redemption — must succeed
        first = client.post("/mix/process", json=payload)
        assert first.status_code == 200, f"First use should succeed: {first.text}"

        # Second redemption — must be blocked
        second = client.post("/mix/process", json=payload)
        assert second.status_code == 403, (
            f"Double-spend should be rejected: {second.status_code} {second.text}"
        )
        detail = second.json()["detail"].lower()
        assert "spent" in detail, f"Unexpected detail: {detail}"

    # ── Bonus Test 5: Missing token when required ─────────────────────────────

    def test_missing_token_rejected_with_403(self, client: TestClient):
        """
        When VEIL_TOKEN_REQUIRED=true and no token is included, the endpoint
        must return HTTP 403 with 'required' in the detail.
        """
        resp = client.post("/mix/process", json={
            "packet_hex": "00ff00ff" * 4,
            # no 'token' field
            "node_id":    "test-node-notoken",
        })
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}: {resp.text}"
        detail = resp.json()["detail"].lower()
        assert "required" in detail, f"Unexpected detail: {detail}"

    # ── Bonus Test 6: usage_acknowledgment is SHA-256 of serial ──────────────

    def test_usage_acknowledgment_matches_serial_hash(
        self,
        client: TestClient,
        issuer: TokenIssuer,
    ):
        """
        The usage_acknowledgment field must equal SHA-256(serial) in hex,
        proving that bandwidth was attributed to the correct token.
        """
        serial, token_hex = make_valid_token(issuer)
        resp = client.post("/mix/process", json={
            "packet_hex": "feedface" * 4,
            "token":      token_hex,
            "node_id":    "test-node-ack",
        })
        assert resp.status_code == 200, resp.text
        expected_ack = hashlib.sha256(serial).hexdigest()
        assert resp.json()["usage_acknowledgment"] == expected_ack, (
            "usage_acknowledgment must be the SHA-256 of the token serial"
        )
