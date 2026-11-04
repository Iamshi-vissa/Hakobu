"""Converter engines. List order is priority order when engines overlap on a pair."""

from __future__ import annotations

from engines.base import Engine
from engines.document import DocumentEngine, PandocEngine
from engines.image import ImageEngine

ALL_ENGINES: list[Engine] = [
    ImageEngine(),
    PandocEngine(),
    DocumentEngine(),
]
