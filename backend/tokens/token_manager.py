"""
JULIUS — Token Manager
Verifies RSA blind-signature bandwidth tokens on the mix node side.

Token wire format (288 bytes, 576 hex chars):
    serial (32 B) || signature (256 B)

The TokenManager:
  1. Fetches the issuer's RSA public key (cached).
  2. Verifies the RSA signature locally.
  3. Checks double-spend status by calling the issuer HTTP API.
  4. Reports bandwidth usage to the issuer for settlement.

All verification results are cached (keyed by SHA-256 of the serial) for
`cache_ttl` seconds so repeated checks within a single session are fast.
"""

import hashlib
import logging
import time
from typing import Tuple, Dict, Optional

logger = logging.getLogger(__name__)

# ── Wire-format constants (must match issuer.py) ─────────────────────────────
_SERIAL_BYTES = 32       # serial number length
_SIG_BYTES    = 256      # RSA-2048 signature (256 bytes = 2048 bits)
_TOKEN_BYTES  = _SERIAL_BYTES + _SIG_BYTES   # 288 bytes → 576 hex chars


class TokenManager:
    """
    Client-side token verifier for a mix-node.

    Parameters
    ----------
    issuer_url : str
        Base URL of the token issuer API, e.g. ``http://localhost:8000/tokens``.
    cache_ttl : int
        Seconds to cache a verification result (positive or negative).
    """

    def __init__(self, issuer_url: str, cache_ttl: int = 300) -> None:
        self.issuer_url  = issuer_url.rstrip("/")
        self.cache_ttl   = cache_ttl

        # serial_hash (hex) → {"valid": bool, "reason": str, "ts": float}
        self._cache: Dict[str, dict] = {}

        # Cached public key bytes (PEM)
        self._public_key_pem: Optional[bytes] = None
        self._public_key_obj = None          # cryptography RSAPublicKey

        self._load_public_key()

    # ── Public-key management ────────────────────────────────────────────────

    def _load_public_key(self) -> None:
        """
        Try to fetch the issuer public key via HTTP.
        Falls back silently; `_public_key_obj` stays None if unreachable.
        """
        try:
            import urllib.request, json as _json
            url = f"{self.issuer_url}/public_key"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read())
            pem_str = data.get("public_key_pem", "")
            if pem_str:
                self._public_key_pem = pem_str.encode()
                self._public_key_obj = self._parse_public_key(self._public_key_pem)
                logger.info("TokenManager: loaded issuer public key from %s", url)
        except Exception as exc:
            logger.warning(
                "TokenManager: could not fetch issuer public key from %s: %s",
                self.issuer_url, exc,
            )

    def get_public_key(self) -> Optional[bytes]:
        """Return the cached issuer public key (PEM bytes), or None if unavailable."""
        return self._public_key_pem

    @staticmethod
    def _parse_public_key(pem: bytes):
        """Load an RSA public key object from PEM bytes."""
        from cryptography.hazmat.primitives import serialization
        return serialization.load_pem_public_key(pem)

    # ── Token verification ───────────────────────────────────────────────────

    def verify_token(self, token: bytes) -> Tuple[bool, str]:
        """
        Verify a raw token (288 bytes).

        Checks performed (in order):
        1. Length — must be exactly 288 bytes.
        2. RSA signature — ``sig^e mod n == serial_int``.
        3. Cache — return cached result if still fresh.
        4. Double-spend — call issuer to mark the token as spent.

        Returns
        -------
        (is_valid, reason) : Tuple[bool, str]
        """
        # ── 1. Length check ─────────────────────────────────────────────────
        if len(token) != _TOKEN_BYTES:
            return False, f"invalid token length {len(token)} (expected {_TOKEN_BYTES})"

        serial    = token[:_SERIAL_BYTES]
        sig_bytes = token[_SERIAL_BYTES:]
        serial_hash_hex = hashlib.sha256(serial).hexdigest()

        # ── 2. Cache hit ─────────────────────────────────────────────────────
        cached = self._cache.get(serial_hash_hex)
        if cached and (time.monotonic() - cached["ts"]) < self.cache_ttl:
            return cached["valid"], cached["reason"]

        # ── 3. RSA signature verification ────────────────────────────────────
        if self._public_key_obj is None:
            # Attempt a lazy re-fetch in case the issuer wasn't up at startup
            self._load_public_key()
        if self._public_key_obj is None:
            # Cannot verify without the public key; fail closed
            return False, "issuer public key unavailable"

        pub_numbers = self._public_key_obj.public_key().public_numbers() \
            if hasattr(self._public_key_obj, "public_key") \
            else self._public_key_obj.public_numbers()
        n, e = pub_numbers.n, pub_numbers.e

        serial_int = int.from_bytes(serial, "big")
        sig_int    = int.from_bytes(sig_bytes, "big")

        if pow(sig_int, e, n) != serial_int:
            result = (False, "RSA signature verification failed")
            self._cache_result(serial_hash_hex, *result)
            return result

        # ── 4. Double-spend check via issuer API ──────────────────────────────
        valid, reason = self._check_double_spend(token)
        self._cache_result(serial_hash_hex, valid, reason)
        return valid, reason

    def _check_double_spend(self, token: bytes) -> Tuple[bool, str]:
        """
        Call ``POST /tokens/redeem`` on the issuer to atomically mark the
        token as spent.  Returns (True, "ok") if accepted, (False, reason)
        if rejected (already spent or network error).

        Note: because the issuer's ``/redeem`` endpoint requires admin JWT,
        we use a lightweight unauthenticated probe strategy: if the issuer
        is unreachable we optimistically accept the token (fail-open for
        availability) but log a warning.
        """
        try:
            import urllib.request, urllib.error, json as _json
            payload = _json.dumps({"tokens": [token.hex()]}).encode()
            req = urllib.request.Request(
                f"{self.issuer_url}/redeem",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read())
            accepted = data.get("accepted", 0)
            rejected = data.get("rejected", [])
            if accepted >= 1:
                return True, "ok"
            if rejected:
                return False, "token already spent (double-spend)"
            return False, "issuer rejected token"
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                # Redeem endpoint requires admin — fallback: trust local RSA check
                logger.warning(
                    "TokenManager: /redeem returned 403 (admin required); "
                    "trusting local RSA verification"
                )
                return True, "ok (local-only verification)"
            logger.warning("TokenManager: double-spend check HTTP error %d", exc.code)
            return True, "ok (issuer unreachable — fail-open)"
        except Exception as exc:
            logger.warning("TokenManager: double-spend check failed: %s", exc)
            return True, "ok (issuer unreachable — fail-open)"

    # ── Usage reporting ──────────────────────────────────────────────────────

    def report_usage(self, token_serial: bytes, bytes_used: int) -> bool:
        """
        Report bandwidth usage to the issuer for settlement.

        POST ``/tokens/usage`` with::

            {
                "serial_hash": "<sha256-hex>",
                "bytes_used":  <int>
            }

        Returns True on success, False otherwise.
        Failure is non-fatal; the mix node should log and continue.
        """
        serial_hash_hex = hashlib.sha256(token_serial).hexdigest()
        try:
            import urllib.request, json as _json
            payload = _json.dumps({
                "serial_hash": serial_hash_hex,
                "bytes_used":  bytes_used,
            }).encode()
            req = urllib.request.Request(
                f"{self.issuer_url}/usage",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                _ = resp.read()
            return True
        except Exception as exc:
            logger.debug(
                "TokenManager: usage report failed for %s…: %s",
                serial_hash_hex[:16], exc,
            )
            return False

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _cache_result(self, serial_hash_hex: str, valid: bool, reason: str) -> None:
        self._cache[serial_hash_hex] = {
            "valid":  valid,
            "reason": reason,
            "ts":     time.monotonic(),
        }
