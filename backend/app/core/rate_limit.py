import time
from collections import deque

from app.core.exceptions import AppError

_hits: dict[str, deque[float]] = {}


def rate_limit(key: str, limit: int, window_s: int) -> None:
    # ponytail: per-process limits; use shared storage before running multiple instances.
    now = time.monotonic()
    hits = _hits.setdefault(key, deque())
    while hits and hits[0] <= now - window_s:
        hits.popleft()
    if len(hits) >= limit:
        raise AppError(429, "rate_limited", "Too many requests, try again shortly")
    hits.append(now)


def prune(window_s: int = 86400) -> None:
    cutoff = time.monotonic() - window_s
    stale: list[str] = []
    for key, hits in _hits.items():
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if not hits:
            stale.append(key)
    for key in stale:
        del _hits[key]
