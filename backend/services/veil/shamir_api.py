"""REAL Shamir Secret Sharing API - 5-of-5 Distributed Rendezvous."""

import json
from typing import List, Tuple
from pydantic import BaseModel
from .rendezvous_real import ShamirSecretSharing
import base64


class SplitSecretRequest(BaseModel):
    secret: str  # Base64 encoded secret or plain text
    n: int = 5   # Total shares
    k: int = 5   # Threshold (must be 5 for 5-of-5)
    encode: str = "base64"  # base64 or hex


class ReconstructSecretRequest(BaseModel):
    shares: List[dict]  # [{"x": 1, "y": "hex_string"}, ...]
    encode: str = "base64"


class RendezvousRequest(BaseModel):
    session_key: str  # Base64 encoded session key
    rp_count: int = 5  # Number of rendezvous points (5)


class RendezvousReconstructRequest(BaseModel):
    shares: List[dict]  # At least 3 shares to reconstruct