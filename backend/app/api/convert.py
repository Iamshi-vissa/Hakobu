"""Start conversion jobs (single file or PDF merge)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.errors import ApiError, ErrorCode
from app.formats import FORMATS
from app.models import ConvertRequest, FileRecord, JobRecord, JobResponse, JobStatus, MergeRequest
from app.naming import checked_id, new_id, stem_of
from app.queue import dispatch
from app.ratelimit import rate_limit
from app.storage import get_storage
from app.store import cached_job_id, get_file, get_job, save_job
from registry import UnsupportedConversion, get_registry

router = APIRouter(dependencies=[Depends(rate_limit)])

MERGEABLE = frozenset({"pdf", "png", "jpg", "webp", "gif", "bmp", "tiff"})


async def _load_file(file_id: str) -> FileRecord:
    record = await get_file(checked_id(file_id, "file"))
    if record is None:
        raise ApiError(404, ErrorCode.NOT_FOUND, "That file doesn't exist or has expired.")
    return record


async def _from_cache(cache_key: str, record: FileRecord, target: str) -> JobRecord | None:
    """A finished job with identical input bytes, target and options, re-labelled for this file."""
    cached_id = await cached_job_id(cache_key)
    cached = await get_job(cached_id) if cached_id else None
    if cached is None or cached.status != JobStatus.DONE or not cached.output_key:
        return None
    if not get_storage().exists(cached.output_key):
        return None
    ext = "zip" if cached.output_count > 1 else FORMATS[target].extension
    return cached.model_copy(
        update={
            "id": new_id(),
            "file_ids": [record.id],
            "output_name": f"{stem_of(record.name)}.{ext}",
        }
    )


@router.post("/convert", response_model=JobResponse)
async def convert(request: ConvertRequest) -> JobResponse:
    record = await _load_file(request.file_id)
    target = request.target_format.lower()
    if target not in FORMATS:
        raise ApiError(422, ErrorCode.UNSUPPORTED_CONVERSION, f"Unknown target format “{target}”.")
    try:
        steps = get_registry().plan(record.format, target, request.options)
    except UnsupportedConversion as exc:
        raise ApiError(422, ErrorCode.UNSUPPORTED_CONVERSION, str(exc)) from None

    cache_key = f"{record.sha256}:{target}:{request.options.cache_key()}" if steps else None
    if cache_key and (hit := await _from_cache(cache_key, record, target)):
        await save_job(hit)
        return JobResponse.of(hit)

    job = JobRecord(id=new_id(), file_ids=[record.id], target=target, options=request.options, cache_key=cache_key)
    await save_job(job)
    await dispatch(job.id)
    return JobResponse.of(await get_job(job.id) or job)


@router.post("/merge", response_model=JobResponse)
async def merge(request: MergeRequest) -> JobResponse:
    records = [await _load_file(fid) for fid in request.file_ids]
    if bad := [r.name for r in records if r.format not in MERGEABLE]:
        raise ApiError(
            422, ErrorCode.UNSUPPORTED_CONVERSION, f"Only PDFs and images can be merged ({', '.join(bad)} can't)."
        )
    job = JobRecord(id=new_id(), file_ids=[r.id for r in records], target="pdf")
    await save_job(job)
    await dispatch(job.id)
    return JobResponse.of(await get_job(job.id) or job)
