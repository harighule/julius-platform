"""REAL Blind Signatures API - Chaum eCash Bandwidth Tokens."""

from pydantic import BaseModel
from typing import Optional
from .tokens_real import RealBlindSignatureToken
import base64


class IssueTokenRequest(BaseModel):
    amount: int = 100  # Bandwidth units
    currency: str = "BANDWIDTH"


class VerifyTokenRequest(BaseModel):
    token: str  # Base64 encoded token


class RedeemTokenRequest(BaseModel):
    token: str
    node_id: str


# Global token issuer instance
_token_issuer = None


def get_token_issuer():
    global _token_issuer
    if _token_issuer is None:
        _token_issuer = RealBlindSignatureToken()
        _token_issuer.generate_issuer_keys()
    return _token_issuer