"""E-books via Calibre's ``ebook-convert``."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from engines.base import ConversionOptions, Engine, Pair, ProgressFn, formats_of, pairs, run_subprocess

EBOOKS = ("epub", "mobi", "azw3")
_PERCENT = re.compile(r"^\s*(\d{1,3})%")
# Calibre renders PDFs with Qt WebEngine; run it headless and without the Chromium
# sandbox (containers lack the namespaces it needs; input is already isolated per job).
CALIBRE_ENV = {
    "QT_QPA_PLATFORM": "offscreen",
    "QTWEBENGINE_DISABLE_SANDBOX": "1",
    "QTWEBENGINE_CHROMIUM_FLAGS": "--no-sandbox --disable-gpu",
}


class EbookEngine(Engine):
    name = "calibre"
    # Reflowing a PDF into an e-book only makes sense for a real PDF, not one made mid-chain.
    entry_only_pairs = pairs(("pdf",), EBOOKS)

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs((*EBOOKS, "pdf"), EBOOKS) | pairs(EBOOKS, ("pdf", "docx", "txt", "rtf"))

    def available(self) -> bool:
        return shutil.which("ebook-convert") is not None

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        formats_of(input_path, output_path)  # validates both extensions

        def on_line(line: str) -> None:
            if progress and (match := _PERCENT.match(line)):
                progress(int(match.group(1)) / 100)

        run_subprocess(
            ["ebook-convert", input_path, output_path],
            env={**os.environ, **CALIBRE_ENV},
            on_line=on_line,
        )
        return [output_path]
