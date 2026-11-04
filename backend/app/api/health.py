"""Liveness/readiness probe."""

from __future__ import annotations

import shutil

from fastapi import APIRouter

from app.models import HealthResponse
from app.redis_client import get_async_redis

router = APIRouter()

TOOLS = ("ffmpeg", "soffice", "pandoc", "ebook-convert", "gs")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        redis_ok = bool(await get_async_redis().ping())
    except Exception:
        redis_ok = False
    tools = {tool: shutil.which(tool) is not None for tool in TOOLS}
    return HealthResponse(status="ok" if redis_ok else "degraded", redis=redis_ok, tools=tools)
