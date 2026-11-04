"""Job status: one-shot JSON and a Server-Sent Events stream of live progress."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.errors import ApiError, ErrorCode
from app.models import JobRecord, JobResponse, JobStatus
from app.naming import checked_id
from app.redis_client import get_async_redis
from app.store import get_job, job_channel, job_event

router = APIRouter()

KEEPALIVE_SECONDS = 15.0
TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED})


async def load_job(job_id: str) -> JobRecord:
    job = await get_job(checked_id(job_id, "job"))
    if job is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "That job doesn't exist or has expired.")
    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: str) -> JobResponse:
    return JobResponse.of(await load_job(job_id))


@router.get("/jobs/{job_id}/events", response_class=StreamingResponse)
async def job_events(job_id: str, request: Request) -> StreamingResponse:
    await load_job(job_id)  # 404 before opening a stream

    async def stream() -> AsyncIterator[str]:
        pubsub = get_async_redis().pubsub()
        await pubsub.subscribe(job_channel(job_id))
        try:
            # Read the snapshot *after* subscribing so no update can slip between the two.
            job = await get_job(job_id)
            if job is None:
                return
            yield f"data: {job_event(job)}\n\n"
            if job.status in TERMINAL:
                return
            while not await request.is_disconnected():
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=KEEPALIVE_SECONDS)
                if message is None:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {message['data']}\n\n"
                if json.loads(message["data"])["status"] in TERMINAL:
                    return
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive",
    })
