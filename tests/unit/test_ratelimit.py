"""Unit tests for the token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import os
from unittest import mock

import pytest

from hip.gateway.ratelimit import RateLimiter, rate_limiter_from_env

pytestmark = pytest.mark.unit


def test_allows_up_to_capacity_then_throttles() -> None:
    async def run() -> list[bool]:
        limiter = RateLimiter(rate=2, per_seconds=60)
        return [await limiter.allow("client") for _ in range(3)]

    assert asyncio.run(run()) == [True, True, False]


def test_keys_are_independent() -> None:
    async def run() -> tuple[bool, bool]:
        limiter = RateLimiter(rate=1, per_seconds=60)
        first = await limiter.allow("a")
        other = await limiter.allow("b")  # different client, own bucket
        return first, other

    assert asyncio.run(run()) == (True, True)


def test_tokens_refill_over_time() -> None:
    async def run() -> list[bool]:
        limiter = RateLimiter(rate=1, per_seconds=0.05)  # refills quickly
        first = await limiter.allow("c")
        blocked = await limiter.allow("c")
        await asyncio.sleep(0.08)
        refilled = await limiter.allow("c")
        return [first, blocked, refilled]

    assert asyncio.run(run()) == [True, False, True]


def test_from_env_disabled_by_default() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        assert rate_limiter_from_env() is None
    with mock.patch.dict(os.environ, {"HIP_RATE_LIMIT": "0"}):
        assert rate_limiter_from_env() is None


def test_from_env_enabled_when_set() -> None:
    with mock.patch.dict(os.environ, {"HIP_RATE_LIMIT": "5", "HIP_RATE_WINDOW_SECONDS": "60"}):
        limiter = rate_limiter_from_env()
    assert limiter is not None
