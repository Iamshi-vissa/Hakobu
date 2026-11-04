"""Job dispatch: RQ in production, inline execution when ``HAKOBU_SYNC_JOBS`` is set."""

from __future__ import annotations

from functools import lru_cache

import anyio
from rq import Callback, Queue

from app.config import get_settings
from app.redis_client import get_redis
from workers.tasks import mark_failed, run_conversion


@lru_cache
def get_queue() -> Queue:
    return Queue(get_settings().queue_name, connection=get_redis())


def _enqueue(job_id: str) -> None:
    settings = get_settings()
    get_queue().enqueue(
        run_conversion, job_id,
        job_id=job_id,
        job_timeout=settings.job_timeout_seconds,
        result_ttl=0,  # results live in our own job record
        failure_ttl=settings.file_ttl_seconds,
        on_failure=Callback(mark_failed),
    )


async def dispatch(job_id: str) -> None:
    if get_settings().sync_jobs:
        await anyio.to_thread.run_sync(run_conversion, job_id)
    else:
        await anyio.to_thread.run_sync(_enqueue, job_id)
