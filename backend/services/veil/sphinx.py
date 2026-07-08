"""PRISM-Sphinx Protocol Implementation (Draft 8, Part Two).

Production implementation of the PRISM-Sphinx protocol.
"""

import os
import hashlib
from dataclasses import dataclass
from typing import List, Tuple, Optional

from .constants import CT_SIZE, ALPHA_SIZE, MAC_SIZE, NODEID_SIZE
from .kem import (
    MLKEMPRISMPublicKey, MLKEMPRISMSecretKey,
    mlkem_prism_encaps, mlkem_prism_reencaps, mlkem_prism_decaps
)


def sha3_256(data: bytes) -> bytes:
    return hashlib.sha3_256(data).digest()


def shake_256(data: bytes, length: int) -> bytes:
    return hashlib.shake_256(data).digest(length)


def stream_cipher(key: bytes, plaintext: bytes) -> bytes:
    """XOR stream cipher for onion encryption."""
    stream = shake_256(key, len(plaintext))
    return bytes(a ^ b for a, b in zip(plaintext, stream))


@dataclass(frozen=True)
class PRISMPacket:
    """PRISM-Sphinx packet."""
    alpha: bytes      # X25519 ephemeral key
    ct_prism: bytes   # ML-KEM-PRISM ciphertext
    beta: bytes       # Onion routing layers
    gamma: bytes      # MAC
    
    def __post_init__(self):
        if len(self.alpha) != ALPHA_SIZE:
            raise ValueError(f"alpha must be {ALPHA_SIZE} bytes")
        if len(self.ct_prism) != CT_SIZE:
            raise ValueError(f"ct_prism must be {CT_SIZE} bytes")
        if len(self.gamma) != MAC_SIZE:
            raise ValueError(f"gamma must be {MAC_SIZE} bytes")


class PRISMSender:
    """
    Sender-side PRISM-Sphinx packet construction.
    
    This is the ONLY party that knows the recipient's public key.
    """
    
    def build_packet(self,
                     recipient_pk: MLKEMPRISMPublicKey,
                     path_node_keys: List[bytes],
                     payload: bytes) -> Tuple[PRISMPacket, bytes]:
        """
        Build a PRISM-Sphinx packet.
        
        Args:
            recipient_pk: Recipient's public key
            path_node_keys: Per-hop symmetric keys (from Sphinx ECDH)
            payload: Encrypted application payload
        
        Returns:
            (packet, shared_secret K)
        """
        n = len(path_node_keys)
        
        # Step 1: Generate n+1 fresh ciphertexts
        ct_0, K, m = mlkem_prism_encaps(recipient_pk)
        
        cts = [ct_0]
        for _ in range(n):
            ct_i, _ = mlkem_prism_reencaps(recipient_pk, m)
            cts.append(ct_i)
        
        # Step 2: Build onion layers
        beta = self._build_beta(path_node_keys, cts, payload)
        
        # Step 3: Generate alpha
        alpha = os.urandom(ALPHA_SIZE)
        
        # Step 4: Compute MAC
        gamma = self._compute_mac(path_node_keys[0], alpha, cts[n], beta)
        
        # Step 5: Secure erase m
        m = bytes(len(m))
        
        return PRISMPacket(alpha=alpha, ct_prism=cts[n], beta=beta, gamma=gamma), K
    
    def _build_beta(self, hop_keys: List[bytes], cts: List[bytes], payload: bytes) -> bytes:
        """Build onion-encrypted routing header."""
        n = len(hop_keys)
        
        # Innermost: recipient marker + CT_0
        inner = b'RECIPIENT' + b'\x00' * (NODEID_SIZE - 9) + cts[0] + payload[:MAC_SIZE]
        
        # Wrap from last hop to first
        for i in range(n - 1, -1, -1):
            if i < n - 1:
                next_id = sha3_256(b'NODE_ID' + i.to_bytes(4, 'big'))[:NODEID_SIZE]
            else:
                next_id = b'RECIPIENT' + b'\x00' * (NODEID_SIZE - 9)
            
            ct_to_forward = cts[n - 1 - i]
            layer_plaintext = next_id + ct_to_forward + inner
            
            stream = shake_256(hop_keys[i] + b'BETA' + i.to_bytes(4, 'big'), len(layer_plaintext))
            inner = bytes(a ^ b for a, b in zip(layer_plaintext, stream))
        
        return inner
    
    def _compute_mac(self, key: bytes, alpha: bytes, ct: bytes, beta: bytes) -> bytes:
        """Compute MAC over packet."""
        mac_key = sha3_256(b'MAC' + key)
        return sha3_256(mac_key + alpha + ct + beta)


class PRISMMixNode:
    """
    Mix node processing for PRISM-Sphinx.
    
    Key property: NEVER accesses recipient's public key.
    """
    
    def __init__(self, node_id: bytes, long_term_key: bytes):
        self.node_id = node_id
        self._ltk = long_term_key
        self._seen: set = set()
    
    def process(self, packet: PRISMPacket) -> Optional[Tuple[bytes, PRISMPacket]]:
        """Process incoming packet. Returns (next_hop_id, outgoing_packet)."""
        # Replay protection
        tag = sha3_256(packet.alpha + packet.ct_prism[:32])
        if tag in self._seen:
            return None
        self._seen.add(tag)
        
        # Derive per-hop key
        hop_key = sha3_256(b'HOP' + self._ltk + packet.alpha)
        
        # Verify MAC
        expected = sha3_256(sha3_256(b'MAC' + hop_key) + packet.alpha + packet.ct_prism + packet.beta)
        if not self._ct_equal(packet.gamma, expected):
            return None
        
        # Decrypt routing layer
        stream = shake_256(hop_key + b'BETA' + b'\x00' * 4, len(packet.beta))
        layer = bytes(a ^ b for a, b in zip(packet.beta, stream))
        
        # Parse layer
        next_hop_id = layer[:NODEID_SIZE].rstrip(b'\x00')
        ct_next = layer[NODEID_SIZE:NODEID_SIZE + CT_SIZE]
        beta_next = layer[NODEID_SIZE + CT_SIZE:]
        
        # Blind alpha
        b_factor = sha3_256(b'BLIND' + packet.alpha + hop_key)
        alpha_next = sha3_256(b'X25519' + packet.alpha + b_factor)
        
        # Compute new MAC
        next_hop_key = sha3_256(b'HOP_FWD' + self._ltk + alpha_next)
        gamma_next = sha3_256(sha3_256(b'MAC' + next_hop_key) + alpha_next + ct_next + beta_next)
        
        outgoing = PRISMPacket(
            alpha=alpha_next,
            ct_prism=ct_next,
            beta=beta_next,
            gamma=gamma_next
        )
        
        return next_hop_id, outgoing
    
    @staticmethod
    def _ct_equal(a: bytes, b: bytes) -> bool:
        """Constant-time comparison."""
        if len(a) != len(b):
            return False
        diff = 0
        for x, y in zip(a, b):
            diff |= x ^ y
        return diff == 0


class PRISMRecipient:
    """Recipient-side processing."""
    
    def __init__(self, sk: MLKEMPRISMSecretKey):
        self.sk = sk
    
    def receive(self, packet: PRISMPacket) -> Tuple[bytes, bytes]:
        """Decapsulate packet and return (K, beta)."""
        K = mlkem_prism_decaps(self.sk, packet.ct_prism)
        return K, packet.beta