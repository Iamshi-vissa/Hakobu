"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import convert, download, formats, health, jobs, upload
from app.cleanup import sweep_forever
from app.config import get_settings
from app.errors import install_error_handlers
from registry import get_registry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_registry()  # build and cache the format graph once, before serving
    sweeper = asyncio.create_task(sweep_forever())
    try:
        yield
    finally:
        sweeper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sweeper


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Hakobu", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["ETag", "Content-Disposition", "Content-Length"],
    )
    install_error_handlers(app)
    for router in (health.router, formats.router, upload.router, convert.router, jobs.router, download.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
