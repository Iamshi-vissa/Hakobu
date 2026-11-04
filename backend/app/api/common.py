"""Helpers shared by API routers."""

from __future__ import annotations

from app.formats import FORMATS
from app.models import TargetInfo
from registry import get_registry


def target_infos(src: str) -> list[TargetInfo]:
    return [
        TargetInfo(format=t.format, label=FORMATS[t.format].label,
                   category=FORMATS[t.format].category, steps=t.steps)
        for t in get_registry().targets(src)
    ]
