"""Text documents: Pandoc for Markdown/HTML/EPUB paths, LibreOffice for office formats."""

from __future__ import annotations

import shutil
from pathlib import Path

from engines.base import ConversionOptions, Engine, Pair, ProgressFn, formats_of, pairs, run_subprocess
from engines.office import OfficeEngine

PANDOC_READERS = {"md": "gfm", "html": "html", "docx": "docx", "odt": "odt"}
PANDOC_WRITERS = {
    "md": "gfm",
    "html": "html5",
    "docx": "docx",
    "odt": "odt",
    "rtf": "rtf",
    "txt": "plain",
    "epub": "epub3",
}
STANDALONE = frozenset({"html", "rtf", "epub"})
# Writers that run under --sandbox with distro Pandoc builds (docx/odt/epub need data files
# the sandbox blocks there). All conversions also run the safe filter below.
SANDBOXED_WRITERS = frozenset({"md", "html", "rtf", "txt"})
SAFE_FILTER = Path(__file__).with_name("pandoc_safe.lua")


class PandocEngine(Engine):
    name = "pandoc"

    def supported_pairs(self) -> frozenset[Pair]:
        return (
            pairs(("md",), ("html", "docx", "odt", "rtf", "txt", "epub"))
            | pairs(("html",), ("md", "docx", "odt", "epub"))
            | pairs(("docx", "odt"), ("md", "epub"))
            | pairs(("docx",), ("html",))
        )

    def available(self) -> bool:
        return shutil.which("pandoc") is not None

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        src, dst = formats_of(input_path, output_path)
        args: list[str | Path] = [
            "pandoc",
            "-f",
            PANDOC_READERS[src],
            "-t",
            PANDOC_WRITERS[dst],
            "--lua-filter",
            SAFE_FILTER,
            "--metadata",
            f"pagetitle={input_path.stem}",
            "-o",
            output_path,
        ]
        if dst in SANDBOXED_WRITERS:
            args.append("--sandbox")
        if dst in STANDALONE:
            args.append("--standalone")
        run_subprocess([*args, input_path])
        return [output_path]


class DocumentEngine(OfficeEngine):
    """Word-processor formats via LibreOffice (warm unoserver when available)."""

    name = "libreoffice-writer"
    INPUTS = ("docx", "doc", "odt", "rtf", "txt", "html")
    OUTPUTS = ("pdf", "docx", "doc", "odt", "rtf", "txt")
