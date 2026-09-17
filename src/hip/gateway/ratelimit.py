"""Per-client request throttling.

Maps to ``gateway.ratelimit`` in docs/DESIGN.md 1 (SRS 7.1). A token-bucket
limiter keyed per client: each key refills at a steady rate up to a burst
capacity, and a request that finds no token is rejected (HTTP 429). In-memory and
process-local — fine for a single instance / pilot; a shared store (Redis) is the
multi-instance upgrade behind the same interface.

Off by default: only active when ``HIP_RATE_LIMIT`` is configured, so it never
surprises a deployment that hasn't opted in.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass


@dataclass
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """Token-bucket limiter: ``rate`` requests per ``per_seconds`` (also the burst)."""

    def __init__(self, rate: int, per_seconds: float) -> None:
        self._capacity = float(rate)
        self._refill_per_sec = rate / per_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        """Consume one token for ``key``; True if allowed, False if throttled."""
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = _Bucket(tokens=self._capacity - 1.0, updated=now)
                return True
            elapsed = now - bucket.updated
            bucket.tokens = min(self._capacity, bucket.tokens + elapsed * self._refill_per_sec)
            bucket.updated = now
            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True
            return False


def rate_limiter_from_env() -> RateLimiter | None:
    """Build a limiter from ``HIP_RATE_LIMIT`` / ``HIP_RATE_WINDOW_SECONDS``, or
    None when unset/non-positive (throttling disabled)."""
    rate = int(os.environ.get("HIP_RATE_LIMIT", "0"))
    if rate <= 0:
        return None
    per_seconds = float(os.environ.get("HIP_RATE_WINDOW_SECONDS", "60"))
    return RateLimiter(rate, per_seconds)
