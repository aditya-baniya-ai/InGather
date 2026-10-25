"""In-memory sliding-window rate limiter (per process; fine for a single-instance demo)."""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status


class RateLimiter:
    LIMITS = {  # action -> (max hits, window seconds)
        "agent_run": (10, 60),
        "approve_invites": (20, 60),
        "message": (30, 60),
        "login": (10, 60),
        "plan_draft": (10, 60),
        "place_lookup": (10, 60),
    }

    def __init__(self):
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, action: str, key: object) -> None:
        limit, window = self.LIMITS[action]
        now = time.monotonic()
        with self._lock:
            hits = self._hits[(action, str(key))]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "rate_limited")
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()
