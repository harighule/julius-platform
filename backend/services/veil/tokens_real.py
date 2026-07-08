"""REAL Blind Signature Tokens - Chaum eCash for bandwidth markets.

This implements the incentive layer from Draft 1.
"""

import hashlib
import secrets
from typing import Tuple, Optional
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes


class RealBlindSignatureToken:
    """
    REAL Chaum blind signature protocol for bandwidth tokens.
    
    Features:
    - Client blinds token request
    - Issuer signs without seeing serial number
    - Client unblinds to get spendable token
    - Mix node verifies token (cannot link to issuance)
    """
    
    def __init__(self):
        self._issuer_key: Optional[RSAPrivateKey] = None
        self._issuer_public_key: Optional[RSAPublicKey] = None
    
    def generate_issuer_keys(self):
        """Generate RSA keys for token issuer."""
        self._issuer_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        self._issuer_public_key = self._issuer_key.public_key()
    
    def blind_message(self, message: bytes, blinding_factor: int) -> int:
        """
        Blind a message using RSA blinding.
        
        Blind(m) = m * r^e mod n
        """
        if not self._issuer_public_key:
            self.generate_issuer_keys()
        
        n = self._issuer_public_key.public_numbers().n
        e = self._issuer_public_key.public_numbers().e
        
        m_int = int.from_bytes(message, 'big')
        r = blinding_factor
        
        blinded = (m_int * pow(r, e, n)) % n
        return blinded
    
    def sign_blinded(self, blinded: int) -> int:
        """
        Sign a blinded message.
        
        Signature = Blind(m)^d mod n
        """
        if not self._issuer_key:
            self.generate_issuer_keys()
        
        d = self._issuer_key.private_numbers().d
        n = self._issuer_key.public_key().public_numbers().n
        
        return pow(blinded, d, n)
    
    def unblind_signature(self, blinded_signature: int, blinding_factor: int) -> int:
        """
        Unblind signature to get valid signature on original message.
        
        Unblind(s') = s' * r^{-1} mod n
        """
        if not self._issuer_public_key:
            self.generate_issuer_keys()
        
        n = self._issuer_public_key.public_numbers().n
        
        # Compute modular inverse of r
        r_inv = pow(blinding_factor, -1, n)
        signature = (blinded_signature * r_inv) % n
        return signature
    
    def verify_token(self, message: bytes, signature: int) -> bool:
        """
        Verify a token signature.
        """
        if not self._issuer_public_key:
            return False
        
        n = self._issuer_public_key.public_numbers().n
        e = self._issuer_public_key.public_numbers().e
        
        m_int = int.from_bytes(message, 'big')
        verified = pow(signature, e, n)
        
        return verified == m_int
    
    def issue_token(self) -> Tuple[bytes, bytes]:
        """
        Issue a new bandwidth token.
        
        Returns (token, blinding_factor)
        """
        # Generate token serial number
        serial = secrets.token_bytes(32)
        
        # Generate blinding factor
        blinding_factor = secrets.randbits(2048)
        
        # Blind and sign
        blinded = self.blind_message(serial, blinding_factor)
        blinded_sig = self.sign_blinded(blinded)
        signature = self.unblind_signature(blinded_sig, blinding_factor)
        
        # Token is (serial, signature)
        token = serial + signature.to_bytes(256, 'big')
        
        return token, blinding_factor.to_bytes(256, 'big')
    
    def verify_bandwidth_token(self, token: bytes) -> bool:
        """
        Verify a bandwidth token at mix node.
        """
        serial = token[:32]
        signature = int.from_bytes(token[32:], 'big')
        
        return self.verify_token(serial, signature)


# Global instance
_token_issuer = None


def get_token_issuer() -> RealBlindSignatureToken:
    global _token_issuer
    if _token_issuer is None:
        _token_issuer = RealBlindSignatureToken()
        _token_issuer.generate_issuer_keys()
    return _token_issuer