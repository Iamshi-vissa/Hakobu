"""Streamed downloads: a single job's output, or several jobs bundled into one ZIP."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.api.jobs import load_job
from app.errors import ApiError, ErrorCode
from app.formats import FORMATS
from app.models import JobRecord, JobStatus
from app.storage import get_storage
from app.zipstream import iter_zip, unique_names

router = APIRouter()

MAX_BATCH = 200


def _disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _require_done(job: JobRecord) -> str:
    if job.status != JobStatus.DONE or not job.output_key:
        raise ApiError(409, ErrorCode.NOT_READY, "This conversion hasn't finished yet.")
    if not get_storage().exists(job.output_key):
        raise ApiError(404, ErrorCode.NOT_FOUND, "This file has expired; please convert it again.")
    return job.output_key


# Declared before /download/{job_id} so "batch" isn't captured as a job id.
@router.get("/download/batch", response_class=StreamingResponse)
async def download_batch(
    job_ids: Annotated[list[str], Query(min_length=1, max_length=MAX_BATCH)],
) -> StreamingResponse:
    jobs = [await load_job(jid) for jid in dict.fromkeys(job_ids)]
    keys = [_require_done(job) for job in jobs]
    names = unique_names(job.output_name or "file" for job in jobs)
    storage = get_storage()

    def stream() -> Iterator[bytes]:  # sync generator: StreamingResponse runs it in a worker thread
        with ExitStack() as stack:
            paths = [stack.enter_context(storage.local_path(key)) for key in keys]
            yield from iter_zip(zip(names, paths))

    return StreamingResponse(stream(), media_type="application/zip",
                             headers={"Content-Disposition": _disposition("hakobu-files.zip")})


@router.get("/download/{job_id}", response_class=StreamingResponse)
async def download(job_id: str) -> StreamingResponse:
    job = await load_job(job_id)
    key = _require_done(job)
    storage = get_storage()
    name = job.output_name or "file"
    media_type = "application/zip" if job.output_count > 1 else FORMATS[job.target].mime
    return StreamingResponse(storage.iter_bytes(key), media_type=media_type, headers={
        "Content-Disposition": _disposition(name),
        "Content-Length": str(storage.size(key)),
    })
