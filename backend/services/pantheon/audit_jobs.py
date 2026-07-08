from __future__ import annotations

import logging

from ...database import db
from .adapters import audit_store

logger = logging.getLogger(__name__)


def run_audit_snapshot_cycle() -> dict:
    verification = audit_store.verify_chain()
    valid = bool(verification.get("valid", False))
    note = "chain verified" if valid else f"verification failed at {verification.get('failed_at')}"
    snapshot = db.create_pantheon_audit_root_snapshot(valid=valid, verification_note=note)
    logger.debug("Pantheon audit snapshot created: %s", snapshot)
    return snapshot

