"""Redis persistence for file and job records (JSON values that expire with the files).

The API uses the async accessors, workers the sync ones; key layout and
serialisation are shared so both sides always agree.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.config import get_settings
from app.models import FileRecord, JobRecord, JobResponse, JobStatus
from app.redis_client import get_async_redis, get_redis

M = TypeVar("M", bound=BaseModel)


def file_key(file_id: str) -> str:
    return f"file:{file_id}"


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def job_channel(job_id: str) -> str:
    return f"job-events:{job_id}"


def cache_index_key(cache_key: str) -> str:
    return f"cache:{cache_key}"


def _ttl() -> int:
    return get_settings().file_ttl_seconds


def _load(model: type[M], raw: str | bytes | None) -> M | None:
    return model.model_validate_json(raw) if raw else None


def job_event(job: JobRecord) -> str:
    return JobResponse.of(job).model_dump_json()


# ---- async (API) ----

async def save_file(record: FileRecord) -> None:
    await get_async_redis().set(file_key(record.id), record.model_dump_json(), ex=_ttl())


async def get_file(file_id: str) -> FileRecord | None:
    return _load(FileRecord, await get_async_redis().get(file_key(file_id)))


async def save_job(job: JobRecord) -> None:
    redis = get_async_redis()
    await redis.set(job_key(job.id), job.model_dump_json(), ex=_ttl())
    await redis.publish(job_channel(job.id), job_event(job))


async def get_job(job_id: str) -> JobRecord | None:
    return _load(JobRecord, await get_async_redis().get(job_key(job_id)))


async def cached_job_id(cache_key: str) -> str | None:
    return await get_async_redis().get(cache_index_key(cache_key))


# ---- sync (workers) ----

def get_file_sync(file_id: str) -> FileRecord | None:
    return _load(FileRecord, get_redis().get(file_key(file_id)))


def get_job_sync(job_id: str) -> JobRecord | None:
    return _load(JobRecord, get_redis().get(job_key(job_id)))


def save_job_sync(job: JobRecord) -> None:
    redis = get_redis()
    pipe = redis.pipeline()
    pipe.set(job_key(job.id), job.model_dump_json(), ex=_ttl())
    pipe.publish(job_channel(job.id), job_event(job))
    if job.cache_key and job.status == JobStatus.DONE:
        pipe.set(cache_index_key(job.cache_key), job.id, ex=_ttl())
    pipe.execute()
