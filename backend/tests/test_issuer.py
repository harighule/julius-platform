"""
JULIUS — Token Issuer Tests
Tests for the blind-signature bandwidth token system.

Run with:
    python -m pytest backend/tests/test_issuer.py -v
"""

import secrets
import sys
import os

# ── Path bootstrap (mirrors conftest.py) ────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Silence heavy imports during tests
os.environ.setdefault("JULIUS_DEBUG", "0")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("ADMIN_DEFAULT_PASSWORD", "TestAdmin@1234")

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Import the service under test
from backend.tokens.issuer import TokenIssuer

# ── Constants (must match issuer.py) ────────────────────────────────────────
_SERIAL_BYTES = 32
_SIG_BYTES    = 256
_TOKEN_BYTES  = _SERIAL_BYTES + _SIG_BYTES   # 288


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def issuer() -> TokenIssuer:
    """
    Create a fresh in-memory TokenIssuer backed by a freshly generated key.
    We bypass file I/O by injecting a pre-generated PEM directly.
    """
    # Generate a transient RSA-2048 key for the test session
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return TokenIssuer(private_key_pem=priv_pem)


# ── Helper: client-side blind / unblind ─────────────────────────────────────

def client_blind_and_issue(issuer: TokenIssuer):
    """
    Simulate the full client-side blind-signature flow.

    Returns (serial_bytes, token_bytes) where token_bytes can be redeemed.
    """
    pub_numbers = issuer._public_key.public_numbers()
    n, e = pub_numbers.n, pub_numbers.e

    # 1. Random 32-byte serial
    serial = secrets.token_bytes(_SERIAL_BYTES)
    serial_int = int.from_bytes(serial, "big")

    # 2. Random blinding factor (must be < n and coprime with n; secrets.randbits is fine)
    r = secrets.randbits(2048) % n
    if r == 0:
        r = 1

    # 3. Blind:  B = serial_int * r^e mod n
    blinded_int = (serial_int * pow(r, e, n)) % n
    blinded_bytes = blinded_int.to_bytes(_SIG_BYTES, "big")

    # 4. Issuer signs the blinded token
    signed_blinded_bytes = issuer.issue_token(blinded_bytes)
    signed_blinded_int   = int.from_bytes(signed_blinded_bytes, "big")

    # 5. Unblind:  sig = signed_blinded * r^{-1} mod n
    r_inv = pow(r, -1, n)
    sig_int = (signed_blinded_int * r_inv) % n
    sig_bytes = sig_int.to_bytes(_SIG_BYTES, "big")

    # 6. Compose spendable token
    token = serial + sig_bytes
    return serial, token


# ════════════════════════════════════════════════════════════════════════════
# Test 1 — Full issuance flow + signature verification
# ════════════════════════════════════════════════════════════════════════════

class TestIssuanceFlow:
    """Verify that a blinded token can be signed, unblinded, and verified."""

    def test_issue_token_returns_bytes_of_correct_length(self, issuer):
        """issue_token() must return exactly _SIG_BYTES bytes."""
        blinded = secrets.token_bytes(_SIG_BYTES)
        signed  = issuer.issue_token(blinded)
        assert isinstance(signed, bytes), "issue_token must return bytes"
        assert len(signed) == _SIG_BYTES, (
            f"Expected {_SIG_BYTES} bytes, got {len(signed)}"
        )

    def test_full_blind_sign_unblind_verify(self, issuer):
        """
        After the complete blind-sign-unblind cycle, the RSA signature
        must verify against the original serial number.
        """
        serial, token = client_blind_and_issue(issuer)

        # Extract components
        assert len(token) == _TOKEN_BYTES
        recovered_serial = token[:_SERIAL_BYTES]
        sig_bytes        = token[_SERIAL_BYTES:]

        assert recovered_serial == serial, "Serial number must survive the round-trip"

        # Manual RSA verify: sig^e mod n == serial_int
        n   = issuer._public_key.public_numbers().n
        e   = issuer._public_key.public_numbers().e
        sig_int    = int.from_bytes(sig_bytes, "big")
        serial_int = int.from_bytes(serial, "big")

        assert pow(sig_int, e, n) == serial_int, (
            "RSA signature verification failed after unblinding"
        )

    def test_public_key_pem_is_valid(self, issuer):
        """get_public_key() must return a loadable PEM public key."""
        pem = issuer.get_public_key()
        assert pem.startswith(b"-----BEGIN PUBLIC KEY-----"), (
            "Public key must be in SubjectPublicKeyInfo PEM format"
        )
        # Ensure it is loadable
        loaded = serialization.load_pem_public_key(pem)
        assert loaded is not None

    def test_issued_counter_increments(self, issuer):
        """total_issued counter must increase with each issue_token call."""
        before = issuer._total_issued
        issuer.issue_token(secrets.token_bytes(_SIG_BYTES))
        assert issuer._total_issued == before + 1


# ════════════════════════════════════════════════════════════════════════════
# Test 2 — Redemption of valid tokens
# ════════════════════════════════════════════════════════════════════════════

class TestRedemption:
    """Verify that valid tokens are accepted and counters update correctly."""

    def test_redeem_valid_token_returns_accepted_1(self, issuer):
        """A freshly issued valid token must be accepted."""
        _, token = client_blind_and_issue(issuer)
        accepted, rejected = issuer.redeem_tokens([token])
        assert accepted == 1, f"Expected 1 accepted, got {accepted}"
        assert rejected == [], f"Expected no rejections, got {rejected}"

    def test_redeem_increments_total_redeemed(self, issuer):
        """total_redeemed counter must increase after a successful redemption."""
        _, token = client_blind_and_issue(issuer)
        before = issuer._total_redeemed
        issuer.redeem_tokens([token])
        assert issuer._total_redeemed == before + 1

    def test_redeem_invalid_token_is_rejected(self, issuer):
        """A token with a random (invalid) signature must be rejected."""
        bad_token = secrets.token_bytes(_TOKEN_BYTES)
        accepted, rejected = issuer.redeem_tokens([bad_token])
        assert accepted == 0
        assert len(rejected) == 1

    def test_redeem_wrong_length_token_is_rejected(self, issuer):
        """Tokens with the wrong byte length must be rejected."""
        too_short = secrets.token_bytes(10)
        accepted, rejected = issuer.redeem_tokens([too_short])
        assert accepted == 0
        assert len(rejected) == 1

    def test_batch_mixed_tokens(self, issuer):
        """Batch redemption must correctly count valid vs invalid tokens."""
        _, good1 = client_blind_and_issue(issuer)
        _, good2 = client_blind_and_issue(issuer)
        bad = secrets.token_bytes(_TOKEN_BYTES)

        accepted, rejected = issuer.redeem_tokens([good1, bad, good2])
        assert accepted == 2
        assert len(rejected) == 1

    def test_get_status_reflects_redemption(self, issuer):
        """get_status() must return accurate counts after redemption."""
        _, token = client_blind_and_issue(issuer)
        issuer.redeem_tokens([token])

        status = issuer.get_status()
        assert status["total_issued"] >= 1
        assert status["total_redeemed"] >= 1
        assert status["total_active"] == status["total_issued"] - status["total_redeemed"]
        assert "public_key_pem" in status
        assert "BEGIN PUBLIC KEY" in status["public_key_pem"]


# ════════════════════════════════════════════════════════════════════════════
# Test 3 — Double-spend prevention
# ════════════════════════════════════════════════════════════════════════════

class TestDoubleSpendPrevention:
    """The same token must not be redeemable more than once."""

    def test_double_spend_second_attempt_fails(self, issuer):
        """
        Redeeming the same token twice:
          - First call  → accepted=1, rejected=[]
          - Second call → accepted=0, rejected=[<token prefix>]
        """
        _, token = client_blind_and_issue(issuer)

        # First redemption — must succeed
        accepted1, rejected1 = issuer.redeem_tokens([token])
        assert accepted1 == 1, "First redemption must succeed"
        assert rejected1 == []

        # Second redemption — must fail
        accepted2, rejected2 = issuer.redeem_tokens([token])
        assert accepted2 == 0, "Second redemption must be rejected (double-spend)"
        assert len(rejected2) == 1, "Double-spent token must appear in rejected list"

    def test_spent_serial_is_recorded(self, issuer):
        """After redemption, _is_spent() must return True for that serial."""
        import hashlib
        _, token = client_blind_and_issue(issuer)
        serial = token[:_SERIAL_BYTES]
        serial_hash = hashlib.sha256(serial).digest()

        # Not spent yet
        assert not issuer._is_spent(serial_hash)

        issuer.redeem_tokens([token])

        # Now it must be spent
        assert issuer._is_spent(serial_hash)

    def test_triple_spend_all_fail_after_first(self, issuer):
        """
        Three attempts with the same token:
        only the first must succeed.
        """
        _, token = client_blind_and_issue(issuer)

        r1_acc, _ = issuer.redeem_tokens([token])
        r2_acc, _ = issuer.redeem_tokens([token])
        r3_acc, _ = issuer.redeem_tokens([token])

        assert r1_acc == 1
        assert r2_acc == 0
        assert r3_acc == 0

    def test_different_tokens_not_cross_blocked(self, issuer):
        """Spending token A must not block token B."""
        _, token_a = client_blind_and_issue(issuer)
        _, token_b = client_blind_and_issue(issuer)

        # Spend A
        issuer.redeem_tokens([token_a])

        # B must still be redeemable
        accepted, rejected = issuer.redeem_tokens([token_b])
        assert accepted == 1, "Token B must not be blocked by spending token A"
        assert rejected == []
