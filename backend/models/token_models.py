"""
JULIUS — Token Issuer Pydantic Models
Defines request/response schemas for blind-signature bandwidth token operations.
"""

from pydantic import BaseModel, Field
from typing import List


class TokenRequest(BaseModel):
    """
    Request to have a blinded token signed by the issuer.
    
    The client blinds a random serial number before sending it so
    the issuer cannot link the issuance to the later redemption.
    """
    blinded_token: str = Field(
        ...,
        description="Hex-encoded blinded token value (big-endian integer)."
    )


class TokenResponse(BaseModel):
    """
    Response containing the issuer's blind signature on the submitted token.
    
    The client unblinds this value locally to obtain a valid RSA signature
    over the original serial number.
    """
    signed_blinded: str = Field(
        ...,
        description="Hex-encoded blind signature (big-endian integer)."
    )


class RedemptionRequest(BaseModel):
    """
    Request to redeem one or more previously issued tokens.
    
    Each entry is a hex-encoded concatenation of:
        serial (32 bytes) || signature (256 bytes)
    i.e. 288 bytes total → 576 hex characters.
    """
    tokens: List[str] = Field(
        ...,
        min_length=1,
        description="List of hex-encoded tokens to redeem."
    )


class RedemptionResponse(BaseModel):
    """
    Result of a batch redemption attempt.
    """
    accepted: int = Field(
        ...,
        description="Number of tokens successfully redeemed."
    )
    rejected: List[str] = Field(
        default_factory=list,
        description=(
            "List of hex-prefixes (first 16 hex chars) of tokens that were "
            "rejected (invalid signature or already spent)."
        )
    )


class TokenStatus(BaseModel):
    """
    Current statistics for the Token Issuer service.
    """
    total_issued: int = Field(..., description="Total tokens signed since startup.")
    total_redeemed: int = Field(..., description="Total tokens successfully redeemed.")
    total_active: int = Field(..., description="Tokens issued but not yet redeemed.")
    public_key_pem: str = Field(..., description="Issuer RSA public key in PEM format.")
