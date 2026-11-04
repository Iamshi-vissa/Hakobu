"""Per-IP fixed-window rate limiting backed by Redis."""

from __future__ import annotations

import time

from fastapi import Request

from app.config import get_settings
from app.errors import ApiError, ErrorCode
from app.redis_client import get_async_redis

WINDOW_SECONDS = 60


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def rate_limit(request: Request) -> None:
    """FastAPI dependency: reject the request when the caller exceeds the per-minute budget."""
    limit = get_settings().rate_limit_per_minute
    if limit <= 0:
        return
    window = int(time.time()) // WINDOW_SECONDS
    key = f"rl:{client_ip(request)}:{window}"
    redis = get_async_redis()
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.expire(key, WINDOW_SECONDS)
    count, _ = await pipe.execute()
    if count > limit:
        retry_after = WINDOW_SECONDS - int(time.time()) % WINDOW_SECONDS
        raise ApiError(429, ErrorCode.RATE_LIMITED,
                       "Too many requests — please slow down and try again shortly.",
                       retry_after=retry_after)
