"""
JULIUS Auth Router — Login, MFA, Register, Logout, Token management.
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel
from typing import Optional

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# ── Request Models ─────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class MFAVerifyRequest(BaseModel):
    mfa_token: str
    code: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "user"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_bearer(auth_header: str) -> str:
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return auth_header.split(" ", 1)[1]


def _verify_token(token: str) -> dict:
    result = db.verify_jwt_token(token)
    if not result["success"]:
        raise HTTPException(status_code=401, detail=result.get("error", "Invalid token"))
    return result


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/status")
async def auth_status():
    return {
        "available": True,
        "message": "JULIUS authentication system operational",
        "features": ["password", "mfa_totp", "ip_rate_limit", "jwt_blacklist"],
    }


@router.post("/login")
async def login(req: LoginRequest, request: Request):
    ip = _client_ip(request)
    ip_check = db.check_ip_allowed(ip)
    if not ip_check["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again at {ip_check['locked_until']}"
        )
    result = db.authenticate(req.username, req.password)
    if not result["success"]:
        db.record_ip_failure(ip)
        raise HTTPException(status_code=401, detail=result.get("error", "Authentication failed"))
    db.record_ip_success(ip)
    if result.get("totp_enabled"):
        mfa_token = db.create_mfa_session(result["user_id"])
        return {"requires_mfa": True, "mfa_token": mfa_token}
    jwt_token = db.create_jwt_token(result["user_id"], result["username"], result["role"])
    return {
        "requires_mfa": False,
        "token": jwt_token,
        "user": {
            "id": result["user_id"],
            "username": result["username"],
            "role": result["role"],
        },
    }


@router.post("/mfa/verify")
async def mfa_verify(req: MFAVerifyRequest, request: Request):
    ip = _client_ip(request)
    ip_check = db.check_ip_allowed(ip)
    if not ip_check["allowed"]:
        raise HTTPException(status_code=429, detail="Too many failed attempts.")
    user_id = db.consume_mfa_session(req.mfa_token)
    if not user_id:
        db.record_ip_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid or expired MFA session")
    user = db.get_user_by_id(user_id)
    if not user or not user.get("totp_secret"):
        raise HTTPException(status_code=401, detail="MFA not configured")
    if not db.verify_totp(user["totp_secret"], req.code):
        db.record_ip_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    db.record_ip_success(ip)
    jwt_token = db.create_jwt_token(user["id"], user["username"], user["role"])
    return {
        "token": jwt_token,
        "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
    }


@router.post("/register")
async def register(req: RegisterRequest):
    result = db.create_user(req.username, req.password, req.role, req.email)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Registration failed"))
    return {"success": True, "user_id": result["user_id"]}


@router.post("/logout")
async def logout(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    db.revoke_token(token)
    return {"success": True, "message": "Logged out"}


@router.get("/me")
async def get_me(authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    user_data = _verify_token(token)
    user = db.get_user_by_id(user_data["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "user_id": user["id"],
        "username": user["username"],
        "email": user.get("email"),
        "role": user["role"],
        "totp_enabled": bool(user.get("totp_enabled")),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
    }


@router.get("/users")
async def list_users(authorization: str = Header(default="")):
    _verify_token(_extract_bearer(authorization))
    return db.get_all_users()
