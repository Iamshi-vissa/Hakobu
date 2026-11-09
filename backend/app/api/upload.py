"""Streaming, resumable chunked uploads.

Protocol (raw request body, no multipart):

* ``X-File-Name``: URL-encoded original filename (required).
* ``Content-Range: bytes <start>-<end>/<total>``: optional. Omit it to send the whole
  file in one request; include it to upload in sequential chunks.
* ``X-Upload-Id``: returned by the first chunk (HTTP 202) and required on later chunks.

A chunk whose ``start`` doesn't match the bytes already received gets HTTP 409 with
``received`` so the client can resume. The final chunk (or single request) returns the
detected format and the allowed targets.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote

import anyio
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.common import target_infos
from app.config import get_settings
from app.detection import HEAD_SIZE, detect
from app.errors import ApiError, ErrorCode
from app.formats import FORMATS
from app.models import FileRecord, FormatInfo, UploadProgress, UploadResponse
from app.naming import checked_id, new_id, sanitize_filename
from app.ratelimit import rate_limit
from app.redis_client import get_async_redis
from app.storage import StorageLimitExceeded, get_storage
from app.store import save_file

router = APIRouter()

_RANGE_RE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")
HASH_CHUNK = 1024 * 1024


class _Range(BaseModel):
    start: int
    end: int
    total: int


class _Session(BaseModel):
    name: str
    total: int
    received: int = 0


def _session_key(upload_id: str) -> str:
    return f"upload:{upload_id}"


def _parse_range(value: str) -> _Range:
    match = _RANGE_RE.match(value.strip())
    if not match:
        raise ApiError(400, ErrorCode.INVALID_REQUEST, "Malformed Content-Range header.")
    start, end, total = map(int, match.groups())
    if not (start <= end < total):
        raise ApiError(400, ErrorCode.INVALID_REQUEST, "Content-Range is out of bounds.")
    return _Range(start=start, end=end, total=total)


def _too_large() -> ApiError:
    limit = get_settings().max_upload_mb
    return ApiError(413, ErrorCode.TOO_LARGE, f"Files can be at most {limit} MB.", limit_mb=limit)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={202: {"model": UploadProgress}, 409: {}, 413: {}, 415: {}},
)
async def upload(
    request: Request,
    x_file_name: Annotated[str, Header()],
    content_range: Annotated[str | None, Header()] = None,
    x_upload_id: Annotated[str | None, Header()] = None,
) -> UploadResponse | JSONResponse:
    settings = get_settings()
    storage = get_storage()
    redis = get_async_redis()
    rng = _parse_range(content_range) if content_range else None
    if rng and rng.total > settings.max_upload_bytes:
        raise _too_large()

    if x_upload_id is None:
        await rate_limit(request)  # one token per upload, not per chunk
        if rng and rng.start != 0:
            raise ApiError(409, ErrorCode.UPLOAD_CONFLICT, "Upload must start at byte 0.", received=0)
        upload_id = new_id()
        session = _Session(name=sanitize_filename(unquote(x_file_name)), total=rng.total if rng else 0)
    else:
        upload_id = checked_id(x_upload_id, "upload")
        raw = await redis.get(_session_key(upload_id))
        if raw is None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "This upload has expired; please start again.")
        session = _Session.model_validate_json(raw)
        if rng is None or rng.total != session.total or rng.start != session.received:
            raise ApiError(409, ErrorCode.UPLOAD_CONFLICT, "Chunk out of order.", received=session.received)

    # One writer per upload at a time.
    lock = f"upload-lock:{upload_id}"
    if not await redis.set(lock, 1, nx=True, ex=settings.subprocess_timeout_seconds):
        raise ApiError(
            409, ErrorCode.UPLOAD_CONFLICT, "A chunk for this upload is already in flight.", received=session.received
        )
    incoming = f"incoming/{upload_id}"
    try:
        limit = rng.end + 1 if rng else settings.max_upload_bytes
        try:
            session.received = await storage.append(incoming, request.stream(), limit)
        except StorageLimitExceeded:
            storage.delete_prefix(incoming)
            await redis.delete(_session_key(upload_id))
            raise _too_large() from None
        if rng and session.received < rng.total:
            await redis.set(_session_key(upload_id), session.model_dump_json(), ex=settings.file_ttl_seconds)
            if session.received != rng.end + 1:
                raise ApiError(409, ErrorCode.UPLOAD_CONFLICT, "Chunk was truncated.", received=session.received)
            return JSONResponse(
                UploadProgress(upload_id=upload_id, received=session.received).model_dump(), status_code=202
            )
        await redis.delete(_session_key(upload_id))
        return await _finalize(incoming, session.name)
    finally:
        await redis.delete(lock)


async def _finalize(incoming: str, name: str) -> UploadResponse:
    storage = get_storage()
    try:
        head = storage.read_range(incoming, 0, HEAD_SIZE)
        if not head:
            raise ApiError(400, ErrorCode.INVALID_REQUEST, "The file is empty.")
        detection = detect(head, name, read_at=lambda offset, n: storage.read_range(incoming, offset, n))
        if detection.format is None:
            raise ApiError(
                415, ErrorCode.UNSUPPORTED_FORMAT, "Hakobu doesn't recognise this file type.", mime=detection.mime
            )
        fmt = FORMATS[detection.format]
        with storage.local_path(incoming) as path:
            sha256 = await anyio.to_thread.run_sync(_sha256, path)
        file_id = new_id()
        key = f"uploads/{file_id}/source.{fmt.extension}"
        storage.move(incoming, key)
    except BaseException:
        storage.delete_prefix(incoming)
        raise
    record = FileRecord(
        id=file_id, name=name, format=fmt.id, mime=detection.mime, size=storage.size(key), sha256=sha256, key=key
    )
    await save_file(record)
    return UploadResponse(
        file_id=file_id,
        name=name,
        format=FormatInfo.of(fmt.id),
        mime=record.mime,
        size=record.size,
        targets=target_infos(fmt.id),
    )
