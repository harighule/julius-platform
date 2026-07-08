"""Constants for VEIL Protocol.

Based on ML-KEM-768 parameters from Draft 8.
"""

from enum import Enum

# ============================================================
# ML-KEM-768 Parameters (FIPS 203)
# ============================================================
K_RANK = 3          # Module rank
N = 256             # Polynomial degree
Q = 3329            # Prime modulus
ETA1 = 2            # CBD parameter for keygen
ETA2 = 2            # CBD parameter for encaps
DU = 10             # Compression bits for u
DV = 4              # Compression bits for v

# Size constants (bytes)
CT_SIZE = 1088      # Ciphertext: u (960) + v (128)
KEY_SIZE = 32       # Shared secret
PK_SIZE = 1184      # Public key
SK_SIZE = 2400      # Secret key

# Sphinx constants
ALPHA_SIZE = 32     # X25519 ephemeral key
MAC_SIZE = 32       # HMAC-SHA3-256
NODEID_SIZE = 32    # Mix node identifier


class AnonymityLevel(Enum):
    """Anonymity levels from Draft 8, Part Three."""
    TOR_ONLY = 1           # Standard Tor (fast, moderate anonymity)
    MIXNET = 2             # Loopix/Katzenpost (higher latency, stronger)
    PRISM_SPHINX = 3       # Full PRISM-Sphinx (maximum, post-quantum)


class TransactionType(Enum):
    """Types of transactions for escrow service."""
    GOODS = 1
    DATA = 2
    SERVICE = 3
    EXPLOIT = 4
    INTELLIGENCE = 5


class DisputeResolution(Enum):
    """Dispute resolution outcomes."""
    BUYER_WINS = 1
    SELLER_WINS = 2
    SPLIT = 3