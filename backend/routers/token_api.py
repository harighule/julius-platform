"""
JULIUS — Token API Router
Exposes blind-signature bandwidth token endpoints under /tokens/*.

Endpoints
---------
GET  /tokens/public_key   (public)  — Issuer RSA public key (PEM)
POST /tokens/issue        (public)  — Sign a client-blinded token
POST /tokens/redeem       (admin)   — Verify and redeem tokens; prevent double-spend
GET  /tokens/status       (admin)   — Issuer statistics

"Admin" endpoints require a Bearer JWT token with role == "admin".
"""

import logging
from fastapi import APIRouter, HTTPException, Header, Request

from ..models.token_models import (
    TokenRequest,
    TokenResponse,
    RedemptionRequest,
    RedemptionResponse,
    TokenStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tokens", tags=["Token Issuer"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_issuer(request: Request):
    """Retrieve the TokenIssuer instance stored in app.state."""
    issuer = getattr(request.app.state, "token_issuer", None)
    if issuer is None:
        raise HTTPException(
            status_code=503,
            detail="Token Issuer service is not initialised. "
                   "Set VEIL_TOKEN_ISSUER_ENABLED=true and restart.",
        )
    return issuer


def _require_admin(authorization: str) -> None:
    """Validate that the supplied Bearer token belongs to an admin user."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        from ..database import db
        result = db.verify_jwt_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Token verification failed")

    if not result.get("success"):
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid token"))
    if result.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/public_key",
    summary="Issuer public key",
    response_description="RSA public key in PEM format",
)
async def get_public_key(request: Request):
    """
    Return the issuer's RSA-2048 public key in PEM format.

    Clients use this to blind their tokens before submission and to verify
    unblinded signatures locally.
    """
    issuer = _get_issuer(request)
    pem = issuer.get_public_key().decode()
    return {"public_key_pem": pem}


@router.post(
    "/issue",
    response_model=TokenResponse,
    summary="Issue (blind-sign) a token",
)
async def issue_token(body: TokenRequest, request: Request):
    """
    Accept a client-blinded token and return the issuer's blind signature.

    The client should:
    1. Generate a 32-byte random serial number ``s``.
    2. Choose a random blinding factor ``r`` (coprime with ``n``).
    3. Compute ``B = s_int * r^e mod n`` and hex-encode it.
    4. POST ``{"blinded_token": "<hex>"}`` here.
    5. Receive ``signed_blinded`` and unblind: ``sig = signed_blinded * r^{-1} mod n``.
    6. Final spendable token = ``hex(s) + hex(sig)`` (576 hex chars).
    """
    issuer = _get_issuer(request)
    try:
        blinded_bytes = bytes.fromhex(body.blinded_token)
    except ValueError:
        raise HTTPException(status_code=422, detail="blinded_token must be a valid hex string")

    try:
        signed_bytes = issuer.issue_token(blinded_bytes)
    except Exception as exc:
        logger.exception("issue_token failed")
        raise HTTPException(status_code=500, detail=f"Signing failed: {exc}")

    return TokenResponse(signed_blinded=signed_bytes.hex())


@router.post(
    "/redeem",
    response_model=RedemptionResponse,
    summary="Redeem tokens (admin only)",
)
async def redeem_tokens(
    body: RedemptionRequest,
    request: Request,
    authorization: str = Header(default=""),
):
    """
    Verify and redeem a batch of tokens.

    Each token in the list must be a hex string representing
    ``serial (32 bytes) || signature (256 bytes)`` = 576 hex characters.

    Tokens with invalid signatures or that have already been redeemed are
    returned in the ``rejected`` list.

    **Requires admin JWT.**
    """
    _require_admin(authorization)
    issuer = _get_issuer(request)

    raw_tokens = []
    parse_errors = []
    for tok_hex in body.tokens:
        try:
            raw_tokens.append(bytes.fromhex(tok_hex))
        except ValueError:
            parse_errors.append(tok_hex[:16])

    accepted, rejected = issuer.redeem_tokens(raw_tokens)
    rejected.extend(parse_errors)

    return RedemptionResponse(accepted=accepted, rejected=rejected)


@router.get(
    "/status",
    response_model=TokenStatus,
    summary="Issuer statistics (admin only)",
)
async def token_status(
    request: Request,
    authorization: str = Header(default=""),
):
    """
    Return current token issuer statistics.

    **Requires admin JWT.**
    """
    _require_admin(authorization)
    issuer = _get_issuer(request)
    stats = issuer.get_status()
    return TokenStatus(**stats)
