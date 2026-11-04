"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import formats, health, upload
from app.config import get_settings
from app.errors import install_error_handlers
from registry import get_registry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_registry()  # build and cache the format graph once, before serving
    yield


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
    for router in (health.router, formats.router, upload.router):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
