"""In-process sliding-window rate limits for Pantheon mutating routes."""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque

from fastapi import HTTPException

_lock = threading.Lock()
_buckets: dict[tuple[int, str], Deque[float]] = {}

_WINDOW_SEC = 60.0


def reset_pantheon_mutation_rate_limits() -> None:
    with _lock:
        _buckets.clear()


def enforce_pantheon_mutation_rate(
    user_id: int | None,
    route_key: str,
    *,
    max_per_window: int | None = None,
) -> None:
    if user_id is None:
        return
    limit = max_per_window if max_per_window is not None else int(os.getenv("PANTHEON_MUTATION_RATE_PER_MINUTE", "120"))
    if limit <= 0:
        return
    key = (int(user_id), route_key)
    now = time.monotonic()
    cutoff = now - _WINDOW_SEC
    with _lock:
        dq = _buckets.get(key)
        if dq is None:
            dq = deque()
            _buckets[key] = dq
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Pantheon write rate limit exceeded for {route_key} ({limit} per {_WINDOW_SEC:.0f}s)",
            )
        dq.append(now)
