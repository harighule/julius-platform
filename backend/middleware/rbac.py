"""
JULIUS RBAC — Role-Based Access Control middleware.
"""

from fastapi import Depends, HTTPException, Header
from ..database import db

ROLES = {
    "admin": ["*"],
    "analyst": ["read:*", "write:scans", "write:exploits", "write:workflows", "read:darkweb"],
    "operator": ["read:dashboard", "read:events", "read:scans", "write:events"],
    "viewer": ["read:dashboard", "read:events"],
}


def _verify_token(authorization: str = Header(default="")) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    result = db.verify_jwt_token(token)
    if not result["success"]:
        raise HTTPException(401, result.get("error", "Invalid token"))
    return result


def _has_permission(role: str, permission: str) -> bool:
    perms = ROLES.get(role, [])
    if "*" in perms:
        return True
    if permission in perms:
        return True
    action, resource = permission.split(":", 1) if ":" in permission else (permission, "*")
    if f"{action}:*" in perms:
        return True
    if f"read:*" in perms and action == "read":
        return True
    return False


def require_permission(permission: str):
    def check(user: dict = Depends(_verify_token)):
        if not _has_permission(user.get("role", "viewer"), permission):
            raise HTTPException(403, "Insufficient permissions")
        return user
    return check


def get_current_user(authorization: str = Header(default="")) -> dict:
    return _verify_token(authorization)
