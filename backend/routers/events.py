"""
JULIUS Events Router — In-process event bus for cross-module communication.
Subscribers are persisted in the database.
"""

import logging
import time
import uuid
import asyncio
from typing import Optional, List
from fastapi import APIRouter
from pydantic import BaseModel

import httpx

from ..database import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["Event Bus"])


class EventPublish(BaseModel):
    event_type: str
    source: str
    data: dict = {}


class SubscribeRequest(BaseModel):
    event_types: List[str]
    webhook_url: str
    subscriber_id: Optional[str] = None


class UnsubscribeRequest(BaseModel):
    subscriber_id: str


@router.get("/recent")
async def get_recent_events(limit: int = 50, event_type: Optional[str] = None):
    events = db.get_recent_events(limit, event_type)
    return {"events": events, "total": len(events)}


@router.post("/publish")
async def publish_event(event: EventPublish):
    event_id = f"evt_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    db.add_event(event_id, event.event_type, event.source, event.data)

    subs = db.get_active_subscribers(event.event_type)
    for sub in subs:
        if sub.get("callback_url"):
            asyncio.create_task(_deliver_webhook(
                sub["callback_url"],
                {"event_id": event_id, "event_type": event.event_type,
                 "source": event.source, "data": event.data}
            ))

    return {"success": True, "event_id": event_id, "webhooks_triggered": len(subs)}


@router.get("/stats")
async def event_stats():
    stats = db.get_event_stats()
    subs = db.get_all_subscribers()
    sub_counts: dict = {}
    for s in subs:
        et = s["event_type"]
        sub_counts[et] = sub_counts.get(et, 0) + 1
    stats["subscribers"] = sub_counts
    return stats


@router.post("/subscribe")
async def subscribe(req: SubscribeRequest):
    sub_id = req.subscriber_id or f"sub_{uuid.uuid4().hex[:8]}"
    for event_type in req.event_types:
        db.add_subscriber(event_type, f"{sub_id}_{event_type}", req.webhook_url)
    return {"success": True, "subscriber_id": sub_id, "subscribed_to": req.event_types}


@router.post("/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    db.remove_subscriber(req.subscriber_id)
    return {"success": True, "subscriber_id": req.subscriber_id}


@router.get("/subscribers")
async def list_subscribers():
    subs = db.get_all_subscribers()
    grouped: dict = {}
    for s in subs:
        et = s["event_type"]
        if et not in grouped:
            grouped[et] = []
        grouped[et].append(s["callback_url"])
    return grouped


async def _deliver_webhook(url: str, payload: dict, max_retries: int = 3):
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10)
                if resp.status_code < 400:
                    return True
        except Exception:
            pass
        await asyncio.sleep(2 ** attempt)
    logger.warning(f"Webhook delivery failed after {max_retries} attempts: {url}")
    return False
