"""VEIL Protocol Integration for JULIUS.

This module implements the PRISM-Sphinx protocol from Draft 8,
providing post-quantum anonymous routing for JULIUS dark web services.

Manager Requirement: Maximum anonymity for JULIUS operations.
"""

from .constants import (
    CT_SIZE, KEY_SIZE, ALPHA_SIZE, MAC_SIZE, NODEID_SIZE,
    K_RANK, N, Q, ETA1, ETA2, DU, DV,
    AnonymityLevel, TransactionType, DisputeResolution
)
from .kem import (
    MLKEMPRISMPublicKey,
    MLKEMPRISMSecretKey,
    mlkem_prism_keygen,
    mlkem_prism_encaps,
    mlkem_prism_reencaps,
    mlkem_prism_decaps
)
from .transport import VEILTransport, VEILConfig, get_veil_transport
from .revenue import RevenueEngine, RoutingToll, EscrowService
from .sphinx import PRISMPacket, PRISMSender, PRISMMixNode, PRISMRecipient

__all__ = [
    # Constants
    'CT_SIZE', 'KEY_SIZE', 'ALPHA_SIZE', 'MAC_SIZE', 'NODEID_SIZE',
    'K_RANK', 'N', 'Q', 'ETA1', 'ETA2', 'DU', 'DV',
    'AnonymityLevel', 'TransactionType', 'DisputeResolution',
    
    # KEM
    'MLKEMPRISMPublicKey',
    'MLKEMPRISMSecretKey',
    'mlkem_prism_keygen',
    'mlkem_prism_encaps',
    'mlkem_prism_reencaps',
    'mlkem_prism_decaps',
    
    # Transport
    'VEILTransport', 'VEILConfig', 'get_veil_transport',
    
    # Revenue
    'RevenueEngine', 'RoutingToll', 'EscrowService',
    
    # Sphinx
    'PRISMPacket', 'PRISMSender', 'PRISMMixNode', 'PRISMRecipient',
]