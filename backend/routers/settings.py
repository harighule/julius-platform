"""
JULIUS Settings Router — Persistent platform configuration.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, Dict, Any

from ..config import get_editable_settings, update_settings
from ..database import db

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class SettingsUpdate(BaseModel):
    settings: Dict[str, Any]


@router.get("/")
async def get_settings():
    return get_editable_settings()


@router.put("/")
async def save_settings(data: SettingsUpdate):
    update_settings(data.settings)
    return {"status": "saved", "settings": get_editable_settings()}


@router.get("/users")
async def list_users():
    return db.get_all_users()
