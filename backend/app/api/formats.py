"""The full conversion matrix, served with a strong ETag so clients can cache it."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Header, Response

from app.api.common import target_infos
from app.formats import FORMATS
from app.models import FormatInfo, FormatsResponse
from registry import get_registry

router = APIRouter()


@lru_cache
def _matrix() -> tuple[bytes, str]:
    """Serialised matrix and its ETag; built once (the graph never changes at runtime)."""
    body = FormatsResponse(
        formats=[FormatInfo.of(fid) for fid in FORMATS],
        conversions={src: target_infos(src) for src in get_registry().matrix()},
    ).model_dump_json().encode()
    return body, f'"{hashlib.sha256(body).hexdigest()[:32]}"'


@router.get("/formats", response_model=FormatsResponse)
async def formats(if_none_match: Annotated[str | None, Header()] = None) -> Response:
    body, etag = _matrix()
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600"}
    if if_none_match and etag in (tag.strip() for tag in if_none_match.split(",")):
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)
