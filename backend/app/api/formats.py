"""The full conversion matrix, served with a strong ETag so clients can cache it."""

from __future__ import annotations

import gzip
import hashlib
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Header, Response

from app.api.common import target_infos
from app.config import get_settings
from app.formats import FORMATS
from app.models import FormatInfo, FormatsResponse
from registry import get_registry

router = APIRouter()


@lru_cache
def _matrix() -> tuple[bytes, bytes, str]:
    """Serialised matrix (plain and gzipped) and its ETag; built once per process."""
    body = (
        FormatsResponse(
            formats=[FormatInfo.of(fid) for fid in FORMATS],
            conversions={src: target_infos(src) for src in get_registry().matrix()},
            max_upload_mb=get_settings().max_upload_mb,
        )
        .model_dump_json()
        .encode()
    )
    return body, gzip.compress(body, 9), f'"{hashlib.sha256(body).hexdigest()[:32]}"'


@router.get("/formats", response_model=FormatsResponse)
async def formats(
    if_none_match: Annotated[str | None, Header()] = None,
    accept_encoding: Annotated[str | None, Header()] = None,
) -> Response:
    body, gzipped, etag = _matrix()
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600", "Vary": "Accept-Encoding"}
    if if_none_match and etag in (tag.strip() for tag in if_none_match.split(",")):
        return Response(status_code=304, headers=headers)
    if accept_encoding and "gzip" in accept_encoding:
        return Response(gzipped, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(body, media_type="application/json", headers=headers)
