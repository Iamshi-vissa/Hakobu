"""Shared Redis connections (sync for workers/RQ, async for the API)."""

from __future__ import annotations

import redis
import redis.asyncio as aioredis

from app.config import get_settings

_sync: redis.Redis | None = None
_async: aioredis.Redis | None = None


def get_redis() -> redis.Redis:
    global _sync
    if _sync is None:
        _sync = redis.Redis.from_url(get_settings().redis_url)
    return _sync


def get_async_redis() -> aioredis.Redis:
    global _async
    if _async is None:
        _async = aioredis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _async


def set_clients(sync_client: redis.Redis, async_client: aioredis.Redis) -> None:
    """Inject clients (used by tests with fakeredis)."""
    global _sync, _async
    _sync, _async = sync_client, async_client
