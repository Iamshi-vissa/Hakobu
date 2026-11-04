"""Background sweeper that deletes stored files once they outlive the TTL."""

from __future__ import annotations

import asyncio
import logging

import anyio

from app.config import get_settings
from app.storage import get_storage

log = logging.getLogger(__name__)


async def sweep_forever() -> None:
    settings = get_settings()
    while True:
        try:
            removed = await anyio.to_thread.run_sync(get_storage().purge_older_than, settings.file_ttl_seconds)
            if removed:
                log.info("cleanup removed %d expired entries", removed)
        except Exception:  # noqa: BLE001 - the sweeper must survive transient errors
            log.exception("cleanup sweep failed")
        await asyncio.sleep(settings.cleanup_interval_seconds)
