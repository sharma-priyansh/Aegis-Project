"""Redis helpers — advisory/perf only (ADR-009 demotes Redis from correctness path).

Used for: signal deduplication (FR-1.3) and correlation-window state (ADR-018).
NOT used for incident ownership or fencing — those are Kafka + Postgres.
"""
from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from .config import Settings

_client: Optional[aioredis.Redis] = None


def get_redis(settings: Settings) -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def dedup_seen(redis: aioredis.Redis, fingerprint: str, ttl_seconds: int) -> bool:
    """Return True if this fingerprint was already seen within the TTL window.

    Atomic SET NX EX: first writer wins and gets False (not a duplicate); subsequent
    writers within the window get True (duplicate). This makes ingestion idempotent
    against signal floods without a DB round-trip.
    """
    key = f"aegis:dedup:{fingerprint}"
    was_set = await redis.set(key, "1", nx=True, ex=ttl_seconds)
    return not bool(was_set)
