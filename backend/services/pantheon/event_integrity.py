"""Deterministic integrity hash for durable Pantheon events (PR-4)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_pantheon_event_integrity_hash(event: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON of all fields except ``integrity_hash``."""
    preimage = {k: v for k, v in sorted(event.items(), key=lambda kv: kv[0]) if k != "integrity_hash"}
    blob = json.dumps(preimage, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
