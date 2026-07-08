"""
JULIUS — Token Issuer Service
Implements Chaum blind-signature bandwidth tokens backed by RSA-2048.

Protocol overview
-----------------
1. Client generates a random serial number  s  (32 bytes).
2. Client blinds it:  B = s_int * r^e  mod n   (r = random blinding factor).
3. Client sends B (hex) to POST /tokens/issue.
4. Issuer returns  S' = B^d  mod n  (blind signature).
5. Client unblinds:  sig = S' * r^{-1}  mod n.
6. Client token = hex(s) || hex(sig)  (32 + 256 = 288 bytes → 576 hex chars).
7. To spend, client sends the token to POST /tokens/redeem.
8. Issuer verifies  sig^e  mod n == s_int  and checks double-spend.

Key persistence
---------------
Keys are stored as PEM files at the paths configured in config.py so they
survive restarts.  If neither file exists, a fresh key pair is generated and
saved automatically.
"""

import hashlib
import logging
import os
from typing import Tuple, List, Optional, Set

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
_SERIAL_BYTES = 32       # serial number length
_SIG_BYTES    = 256      # RSA-2048 signature length (256 bytes = 2048 bits)
_TOKEN_BYTES  = _SERIAL_BYTES + _SIG_BYTES   # 288 bytes → 576 hex chars


class TokenIssuer:
    """
    RSA blind-signature token issuer.

    Parameters
    ----------
    private_key_pem : bytes | None
        Raw PEM bytes of the RSA private key.  If *None* and no key files
        exist at the configured paths, a new key pair is generated.
    public_key_pem : bytes | None
        Raw PEM bytes of the RSA public key.  Ignored when *private_key_pem*
        is supplied (the public key is derived from it).
    """

    def __init__(
        self,
        private_key_pem: Optional[bytes] = None,
        public_key_pem: Optional[bytes] = None,
    ) -> None:
        self._private_key: Optional[RSAPrivateKey] = None
        self._public_key:  Optional[RSAPublicKey]  = None

        # In-memory spent-token registry (SHA-256 of the serial number)
        self._spent_serials: Set[bytes] = set()

        # Counters
        self._total_issued:   int = 0
        self._total_redeemed: int = 0

        if private_key_pem:
            self._load_keys_from_pem(private_key_pem, public_key_pem)
        else:
            self._load_or_generate_keys()

    # ── Key management ─────────────────────────────────────────────────────

    def _load_keys_from_pem(
        self,
        private_pem: bytes,
        public_pem: Optional[bytes] = None,
    ) -> None:
        """Load an RSA private key (and derive public key) from PEM bytes."""
        self._private_key = serialization.load_pem_private_key(
            private_pem, password=None
        )
        self._public_key = self._private_key.public_key()
        logger.info("TokenIssuer: loaded RSA key pair from supplied PEM bytes")

    def _load_or_generate_keys(self) -> None:
        """
        Try to load keys from the configured PEM files; generate a new pair
        if neither file exists yet.
        """
        # Import config lazily to avoid circular imports
        try:
            from ..config import (
                VEIL_TOKEN_ISSUER_PRIVATE_KEY_FILE,
                VEIL_TOKEN_ISSUER_PUBLIC_KEY_FILE,
            )
            priv_path = VEIL_TOKEN_ISSUER_PRIVATE_KEY_FILE
            pub_path  = VEIL_TOKEN_ISSUER_PUBLIC_KEY_FILE
        except ImportError:
            priv_path = "data/tokens/issuer_private.pem"
            pub_path  = "data/tokens/issuer_public.pem"

        if os.path.isfile(priv_path):
            try:
                with open(priv_path, "rb") as fh:
                    self._private_key = serialization.load_pem_private_key(
                        fh.read(), password=None
                    )
                self._public_key = self._private_key.public_key()
                logger.info("TokenIssuer: loaded existing key pair from %s", priv_path)
                return
            except Exception as exc:
                logger.warning(
                    "TokenIssuer: failed to load key from %s (%s) — generating new keys",
                    priv_path, exc,
                )

        # Generate new 2048-bit RSA key pair
        logger.info("TokenIssuer: generating new RSA-2048 key pair …")
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key = self._private_key.public_key()

        # Persist to disk
        self._save_keys(priv_path, pub_path)

    def _save_keys(self, priv_path: str, pub_path: str) -> None:
        """Write the current key pair to PEM files, creating parent dirs."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(priv_path)), exist_ok=True)
            with open(priv_path, "wb") as fh:
                fh.write(
                    self._private_key.private_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PrivateFormat.TraditionalOpenSSL,
                        encryption_algorithm=serialization.NoEncryption(),
                    )
                )
            with open(pub_path, "wb") as fh:
                fh.write(
                    self._public_key.public_bytes(
                        encoding=serialization.Encoding.PEM,
                        format=serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                )
            logger.info("TokenIssuer: saved key pair to %s / %s", priv_path, pub_path)
        except Exception as exc:
            logger.warning("TokenIssuer: could not persist keys: %s", exc)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_public_key(self) -> bytes:
        """Return the issuer public key as PEM-encoded bytes."""
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def issue_token(self, blinded_token: bytes) -> bytes:
        """
        Blind-sign a token.

        Parameters
        ----------
        blinded_token : bytes
            Raw bytes of the client-blinded token  B = s * r^e mod n,
            encoded as a big-endian integer.

        Returns
        -------
        bytes
            Raw bytes of the blind signature  S' = B^d mod n (big-endian,
            padded to *_SIG_BYTES* bytes).
        """
        n = self._private_key.public_key().public_numbers().n
        d = self._private_key.private_numbers().d

        blinded_int = int.from_bytes(blinded_token, "big")
        signed_int  = pow(blinded_int, d, n)

        self._total_issued += 1
        return signed_int.to_bytes(_SIG_BYTES, "big")

    def redeem_tokens(
        self, tokens: List[bytes]
    ) -> Tuple[int, List[str]]:
        """
        Verify and redeem a batch of tokens.

        Parameters
        ----------
        tokens : list[bytes]
            Each element is a raw token: ``serial (32 B) || signature (256 B)``.

        Returns
        -------
        tuple[int, list[str]]
            *(accepted, rejected)* where *rejected* is a list of short hex
            prefixes identifying the invalid / double-spent tokens.
        """
        accepted  = 0
        rejected: List[str] = []

        n = self._public_key.public_numbers().n
        e = self._public_key.public_numbers().e

        for token in tokens:
            token_hex_prefix = token.hex()[:16]

            if len(token) != _TOKEN_BYTES:
                logger.debug("TokenIssuer: token length mismatch (%d)", len(token))
                rejected.append(token_hex_prefix)
                continue

            serial    = token[:_SERIAL_BYTES]
            sig_bytes = token[_SERIAL_BYTES:]

            serial_int = int.from_bytes(serial, "big")
            sig_int    = int.from_bytes(sig_bytes, "big")

            # Verify RSA signature: sig^e mod n == serial_int
            if pow(sig_int, e, n) != serial_int:
                logger.debug("TokenIssuer: invalid signature for token %s", token_hex_prefix)
                rejected.append(token_hex_prefix)
                continue

            # Double-spend check
            serial_hash = hashlib.sha256(serial).digest()
            if self._is_spent(serial_hash):
                logger.debug("TokenIssuer: double-spend attempt for token %s", token_hex_prefix)
                rejected.append(token_hex_prefix)
                continue

            # Accept
            self._mark_spent(serial_hash)
            self._total_redeemed += 1
            accepted += 1

        return accepted, rejected

    def get_status(self) -> dict:
        """Return current issuer statistics."""
        return {
            "total_issued":   self._total_issued,
            "total_redeemed": self._total_redeemed,
            "total_active":   self._total_issued - self._total_redeemed,
            "public_key_pem": self.get_public_key().decode(),
        }

    # ── Internal helpers ───────────────────────────────────────────────────

    def _is_spent(self, serial_hash: bytes) -> bool:
        """Return True if this serial has already been redeemed."""
        return serial_hash in self._spent_serials

    def _mark_spent(self, serial_hash: bytes) -> None:
        """Record a serial as spent to prevent double-spending."""
        self._spent_serials.add(serial_hash)
