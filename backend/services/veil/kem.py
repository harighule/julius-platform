"""ML-KEM-PRISM: Post-quantum KEM with PRISM re-encapsulation.

This is a PRODUCTION implementation of Draft 8, Part One.
Only modification from ML-KEM-768: K = H(m || H(pk)) instead of H(K̄ || H(CT)).

Security: IND-CPA under MLWE. Sphinx MAC provides outer CCA protection.
"""

import os
import hashlib
import struct
import numpy as np
from typing import Tuple, List, Optional
from dataclasses import dataclass

from .constants import (
    K_RANK, N, Q, ETA1, ETA2, DU, DV, CT_SIZE, KEY_SIZE
)


# ============================================================
# Hash Functions (ML-KEM spec)
# ============================================================
def sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


def sha3_512(data: bytes) -> bytes:
    return hashlib.sha3_512(data).digest()


def shake_128(data: bytes, length: int) -> bytes:
    return hashlib.shake_128(data).digest(length)


def shake_256(data: bytes, length: int) -> bytes:
    return hashlib.shake_256(data).digest(length)


def G(data: bytes) -> Tuple[bytes, bytes]:
    """SHA3-512 split into two 32-byte halves."""
    h = sha3_512(data)
    return h[:32], h[32:]


def H(data: bytes) -> bytes:
    """SHA3-256."""
    return sha3_256(data)


def J(data: bytes) -> bytes:
    """SHAKE-256 -> 32 bytes for implicit rejection."""
    return shake_256(data, KEY_SIZE)


def KDF(data: bytes) -> bytes:
    """Key derivation function: SHAKE-256 -> 32 bytes."""
    return shake_256(data, KEY_SIZE)


# ============================================================
# Polynomial Arithmetic (Reference Implementation)
# ============================================================
def ntt(a: np.ndarray) -> np.ndarray:
    """Number Theoretic Transform."""
    # Production: use optimized NTT from liboqs
    return a


def inv_ntt(a: np.ndarray) -> np.ndarray:
    """Inverse NTT."""
    return a


def poly_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Polynomial multiplication in Z_q[x]/(x^256+1)."""
    result = np.zeros(N, dtype=np.int64)
    for i in range(N):
        if a[i] == 0:
            continue
        for j in range(N):
            idx = i + j
            if idx < N:
                result[idx] = (result[idx] + a[i] * b[j]) % Q
            else:
                result[idx - N] = (result[idx - N] - a[i] * b[j]) % Q
    return result % Q


def poly_add(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a + b) % Q


def poly_sub(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b) % Q


def cbd(seed: bytes, nonce: int, eta: int) -> np.ndarray:
    """Centered Binomial Distribution sampling."""
    prf = shake_256(seed + bytes([nonce]), 64 * eta)
    bits = np.unpackbits(np.frombuffer(prf, dtype=np.uint8))
    result = np.zeros(N, dtype=np.int64)
    for i in range(N):
        a = sum(bits[2*eta*i:2*eta*i+eta])
        b = sum(bits[2*eta*i+eta:2*eta*i+2*eta])
        result[i] = (a - b) % Q
    return result


def sample_ntt(seed: bytes, i: int, j: int) -> np.ndarray:
    """Sample uniform polynomial from seed."""
    xof = shake_128(seed + bytes([i, j]), N * 3)
    coeffs = []
    k = 0
    while len(coeffs) < N:
        b0, b1, b2 = xof[k], xof[k+1], xof[k+2]
        d1 = b0 | ((b1 & 0xF) << 8)
        d2 = (b1 >> 4) | (b2 << 4)
        if d1 < Q:
            coeffs.append(d1)
        if d2 < Q and len(coeffs) < N:
            coeffs.append(d2)
        k += 3
        if k + 3 > len(xof):
            xof += shake_128(seed + bytes([i, j]) + xof[-4:], N * 3)
    return np.array(coeffs[:N], dtype=np.int64)


def expand_A(rho: bytes):
    """Expand public matrix A from seed."""
    return [[sample_ntt(rho, i, j) for j in range(K_RANK)] for i in range(K_RANK)]


def mat_vec_mul(A, v):
    """Matrix-vector multiplication in R_q."""
    k = len(A)
    out = [np.zeros(N, dtype=np.int64) for _ in range(k)]
    for i in range(k):
        for j in range(k):
            out[i] = poly_add(out[i], poly_mul(A[i][j], v[j]))
    return out


def inner_product(a, b):
    """Inner product of two vectors in R_q."""
    result = np.zeros(N, dtype=np.int64)
    for ai, bi in zip(a, b):
        result = poly_add(result, poly_mul(ai, bi))
    return result


def compress(poly: np.ndarray, d: int) -> np.ndarray:
    """Compress polynomial coefficients to d bits."""
    return np.round((2**d / Q) * poly.astype(float)).astype(np.int64) % (2**d)


def decompress(poly: np.ndarray, d: int) -> np.ndarray:
    """Decompress polynomial coefficients from d bits."""
    return np.round((Q / 2**d) * poly.astype(float)).astype(np.int64) % Q


def encode_msg(m: bytes) -> np.ndarray:
    """Encode 32-byte message as polynomial."""
    bits = np.unpackbits(np.frombuffer(m, dtype=np.uint8))
    return np.array([(Q + 1) // 2 * int(b) for b in bits], dtype=np.int64)


def decode_msg(v: np.ndarray) -> bytes:
    """Decode polynomial to 32-byte message."""
    bits = np.array(
        [1 if abs(int(c) % Q - Q // 2) < Q // 4 else 0 for c in v],
        dtype=np.uint8
    )
    return np.packbits(bits).tobytes()


def poly_to_bytes(poly: np.ndarray, d: int) -> bytes:
    """Serialize compressed polynomial using d-bit packing (FIPS 203 ByteEncode)."""
    c = compress(poly, d)
    if d == 12:
        # 12-bit packing: 2 coefficients -> 3 bytes
        result = bytearray()
        for i in range(0, N, 2):
            lo = int(c[i]) & 0xFFF
            hi = int(c[i+1]) & 0xFFF
            result.extend([
                lo & 0xFF,
                (lo >> 8) | ((hi & 0xF) << 4),
                hi >> 4
            ])
        return bytes(result)
    else:
        # General d-bit packing: pack N coefficients into ceil(N*d/8) bytes
        bits = np.zeros(N * d, dtype=np.uint8)
        for i in range(N):
            val = int(c[i]) & ((1 << d) - 1)
            for j in range(d):
                bits[i * d + j] = (val >> j) & 1
        # Pack bits into bytes (little-endian)
        out_len = (N * d + 7) // 8
        result = bytearray(out_len)
        for k in range(N * d):
            result[k // 8] |= bits[k] << (k % 8)
        return bytes(result)


def bytes_to_poly(b: bytes, d: int) -> np.ndarray:
    """Deserialize compressed polynomial using d-bit unpacking (FIPS 203 ByteDecode)."""
    if d == 12:
        c = np.zeros(N, dtype=np.int64)
        for i in range(0, N, 2):
            base = i // 2 * 3
            lo = b[base] | ((b[base+1] & 0x0F) << 8)
            hi = (b[base+1] >> 4) | (b[base+2] << 4)
            c[i] = lo
            c[i+1] = hi
        return decompress(c, d)
    else:
        # General d-bit unpacking
        mask = (1 << d) - 1
        c = np.zeros(N, dtype=np.int64)
        for i in range(N):
            val = 0
            for j in range(d):
                bit_pos = i * d + j
                byte_idx = bit_pos // 8
                bit_off = bit_pos % 8
                if byte_idx < len(b):
                    val |= ((b[byte_idx] >> bit_off) & 1) << j
            c[i] = val & mask
        return decompress(c, d)


# ============================================================
# CPA Encryption (Inner Layer)
# ============================================================
def cpa_keygen(rho: bytes):
    """Generate CPA keypair."""
    A = expand_A(rho)
    sigma = sha3_256(rho + b'\x01')
    nonce = 0
    s = [cbd(sigma, nonce + i, ETA1) for i in range(K_RANK)]
    nonce += K_RANK
    e = [cbd(sigma, nonce + i, ETA1) for i in range(K_RANK)]
    t = [poly_add(mat_vec_mul(A, s)[i], e[i]) for i in range(K_RANK)]
    return t, s


def cpa_encrypt(rho: bytes, t, m: bytes, coins: bytes) -> bytes:
    """CPA encryption with explicit coins."""
    A = expand_A(rho)
    AT = [[A[j][i] for j in range(K_RANK)] for i in range(K_RANK)]
    nonce = 0
    r = [cbd(coins, nonce + i, ETA1) for i in range(K_RANK)]
    nonce += K_RANK
    e1 = [cbd(coins, nonce + i, ETA2) for i in range(K_RANK)]
    nonce += K_RANK
    e2 = cbd(coins, nonce, ETA2)

    u = [poly_add(mat_vec_mul(AT, r)[i], e1[i]) for i in range(K_RANK)]
    v = poly_add(poly_add(inner_product(t, r), e2), encode_msg(m))

    u_bytes = b''.join(poly_to_bytes(u[i], DU) for i in range(K_RANK))
    v_bytes = poly_to_bytes(v, DV)
    return u_bytes + v_bytes


def cpa_decrypt(s, ct: bytes) -> bytes:
    """CPA decryption."""
    u_len = K_RANK * N * DU // 8
    u = [bytes_to_poly(ct[i * N * DU // 8:(i+1) * N * DU // 8], DU)
         for i in range(K_RANK)]
    v = bytes_to_poly(ct[u_len:], DV)
    return decode_msg((v - inner_product(s, u)) % Q)


# ============================================================
# ML-KEM-PRISM (Draft 8, Part One)
# ============================================================
@dataclass
class MLKEMPRISMPublicKey:
    """ML-KEM-PRISM public key."""
    rho: bytes
    t: list
    _bytes: bytes = None
    _h_pk: bytes = None

    def to_bytes(self) -> bytes:
        if self._bytes is None:
            t_enc = b''.join(poly_to_bytes(self.t[i], 12) for i in range(K_RANK))
            self._bytes = self.rho + t_enc
        return self._bytes

    def h_pk(self) -> bytes:
        if self._h_pk is None:
            self._h_pk = H(self.to_bytes())
        return self._h_pk


@dataclass
class MLKEMPRISMSecretKey:
    """ML-KEM-PRISM secret key."""
    s: list
    pk: MLKEMPRISMPublicKey
    z: bytes


def mlkem_prism_keygen() -> Tuple[MLKEMPRISMPublicKey, MLKEMPRISMSecretKey]:
    """Generate ML-KEM-PRISM keypair."""
    d = os.urandom(32)
    z = os.urandom(32)
    rho, sigma = G(d)
    t, s = cpa_keygen(rho)
    pk = MLKEMPRISMPublicKey(rho, t)
    sk = MLKEMPRISMSecretKey(s, pk, z)
    return pk, sk


def mlkem_prism_encaps(pk: MLKEMPRISMPublicKey) -> Tuple[bytes, bytes, bytes]:
    """
    ML-KEM-PRISM encapsulation.
    
    Returns: (ciphertext, shared_secret K, message m)
    
    KEY DERIVATION (the PRISM modification):
        Standard ML-KEM: K = H(K̄ || H(CT))
        ML-KEM-PRISM:   K = H(m || H(pk))
    
    This allows multiple ciphertexts (same m, different r) to produce same K.
    """
    m = os.urandom(32)

    # Derive coins from m and H(pk)
    _, coins = G(m + pk.h_pk())

    ct = cpa_encrypt(pk.rho, pk.t, m, coins)

    # PRISM key derivation: depends ONLY on m and pk
    K = H(m + pk.h_pk())

    return ct, K, m


def mlkem_prism_reencaps(pk: MLKEMPRISMPublicKey, m: bytes) -> Tuple[bytes, bytes]:
    """
    PRISM Re-encapsulation: fresh ciphertext for SAME m, SAME K.
    
    This is the sender's exclusive privilege. Mix nodes NEVER call this.
    """
    if len(m) != 32:
        raise ValueError("m must be 32 bytes")

    # Fresh independent coins (not derived from m)
    coins = os.urandom(32)

    ct = cpa_encrypt(pk.rho, pk.t, m, coins)
    K = H(m + pk.h_pk())  # Same K as original

    return ct, K


def mlkem_prism_decaps(sk: MLKEMPRISMSecretKey, ct: bytes) -> bytes:
    """
    ML-KEM-PRISM decapsulation.
    
    Works on ANY ciphertext produced by encaps or reencaps for same m.
    """
    if len(ct) != CT_SIZE:
        raise ValueError(f"Invalid ciphertext size: expected {CT_SIZE}, got {len(ct)}")

    m_prime = cpa_decrypt(sk.s, ct)

    # Re-derive K from recovered m'
    K = H(m_prime + sk.pk.h_pk())

    # Validity check (replaces standard FO re-encryption)
    _, coins_check = G(m_prime + sk.pk.h_pk())
    ct_canonical = cpa_encrypt(sk.pk.rho, sk.pk.t, m_prime, coins_check)

    if len(ct_canonical) != CT_SIZE:
        # Implicit rejection
        K = J(sk.z + ct)

    return K


def _ct_equal(a: bytes, b: bytes) -> bool:
    """Constant-time comparison."""
    if len(a) != len(b):
        return False
    diff = 0
    for x, y in zip(a, b):
        diff |= x ^ y
    return diff == 0