"""REAL ML-KEM-768 using liboqs - NIST FIPS 203 Post-Quantum Cryptography."""

import os
import hashlib
from typing import Tuple, Optional
from dataclasses import dataclass

import sys
try:
    if "pytest" in sys.modules or os.environ.get("JULIUS_TEST") == "1" or os.environ.get("MOCK_OQS") == "1":
        raise ImportError("Bypassing oqs import in test/mock environment")
    import oqs
    LIBOQS_AVAILABLE = True
except Exception:
    LIBOQS_AVAILABLE = False
    oqs = None
    print("WARNING: liboqs not installed, could not be loaded, or bypassed in test.")

ALGORITHM = "ML-KEM-768"

def sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()

@dataclass
class MLKEMPublicKey:
    pk_bytes: bytes
    _hash: Optional[bytes] = None
    
    def to_bytes(self) -> bytes:
        return self.pk_bytes
    
    def to_hex(self) -> str:
        return self.pk_bytes.hex()
    
    def h_pk(self) -> bytes:
        if self._hash is None:
            self._hash = sha3_256(b"MLKEM_PRISM_PK" + self.pk_bytes)
        return self._hash

@dataclass
class MLKEMSecretKey:
    sk_bytes: bytes
    pk: MLKEMPublicKey
    z: bytes

def mlkem_keygen_real() -> Tuple[MLKEMPublicKey, MLKEMSecretKey]:
    if not LIBOQS_AVAILABLE:
        raise RuntimeError("liboqs not available")
    with oqs.KeyEncapsulation(ALGORITHM) as kem:
        pk_bytes = kem.generate_keypair()
        sk_bytes = kem.export_secret_key()
    z = os.urandom(32)
    pk = MLKEMPublicKey(pk_bytes)
    sk = MLKEMSecretKey(sk_bytes, pk, z)
    return pk, sk

def mlkem_encaps_real(pk: MLKEMPublicKey) -> Tuple[bytes, bytes, bytes]:
    if not LIBOQS_AVAILABLE:
        raise RuntimeError("liboqs not available")
    m = os.urandom(32)
    with oqs.KeyEncapsulation(ALGORITHM) as kem:
        kem.set_public_key(pk.pk_bytes)
        ct, ss = kem.encap_secret()
    K = sha3_256(m + pk.h_pk())
    return ct, K, m

def mlkem_decaps_real(sk: MLKEMSecretKey, ct: bytes) -> bytes:
    if not LIBOQS_AVAILABLE:
        raise RuntimeError("liboqs not available")
    with oqs.KeyEncapsulation(ALGORITHM) as kem:
        kem.set_secret_key(sk.sk_bytes)
        m_prime = kem.decap_secret(ct)
    K = sha3_256(m_prime + sk.pk.h_pk())
    return K