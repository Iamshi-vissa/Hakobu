"""Converter engines. List order is priority order when engines overlap on a pair."""

from __future__ import annotations

from engines.archive import ArchiveEngine
from engines.base import Engine
from engines.data import DataEngine
from engines.document import DocumentEngine, PandocEngine
from engines.ebook import EbookEngine
from engines.image import ImageEngine
from engines.media import MediaEngine
from engines.office import PresentationEngine, SpreadsheetEngine
from engines.pdf import PdfEngine

ALL_ENGINES: list[Engine] = [
    ImageEngine(),
    PandocEngine(),
    DocumentEngine(),
    PdfEngine(),
    DataEngine(),  # before LibreOffice Calc so CSV/data paths stream
    SpreadsheetEngine(),
    PresentationEngine(),
    MediaEngine(),
    EbookEngine(),
    ArchiveEngine(),
]
