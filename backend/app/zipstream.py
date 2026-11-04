"""Incremental ZIP writer: yields archive bytes as they're produced (never buffers files)."""

from __future__ import annotations

import io
import time
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

CHUNK = 1024 * 1024
# Already-compressed formats are stored; everything else gets fast deflate.
_STORED_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".heic", ".mp3", ".m4a", ".aac",
    ".ogg", ".opus", ".flac", ".mp4", ".mov", ".mkv", ".webm", ".zip", ".gz", ".7z",
    ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp", ".epub", ".pdf",
})


class _Sink(io.RawIOBase):
    """Write-only, non-seekable buffer that zipfile writes into and we drain."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def writable(self) -> bool:
        return True

    def write(self, data: bytes) -> int:  # type: ignore[override]
        self._buffer += data
        return len(data)

    def drain(self) -> bytes:
        data = bytes(self._buffer)
        self._buffer.clear()
        return data


def unique_names(names: Iterable[str]) -> list[str]:
    """De-duplicate archive member names: ``a.png, a.png`` → ``a.png, a (2).png``."""
    seen: dict[str, int] = {}
    result = []
    for name in names:
        count = seen.get(name.lower(), 0) + 1
        seen[name.lower()] = count
        if count > 1:
            stem, dot, ext = name.rpartition(".")
            name = f"{stem} ({count}).{ext}" if dot else f"{name} ({count})"
        result.append(name)
    return result


def iter_zip(entries: Iterable[tuple[str, Path]]) -> Iterator[bytes]:
    """Yield a ZIP archive of ``(arcname, path)`` entries chunk by chunk."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=1) as archive:
        for arcname, path in entries:
            member: str | zipfile.ZipInfo = arcname  # str → archive-level fast deflate
            if path.suffix.lower() in _STORED_SUFFIXES:
                member = zipfile.ZipInfo(arcname, time.localtime(path.stat().st_mtime)[:6])
                member.compress_type = zipfile.ZIP_STORED
            with archive.open(member, "w", force_zip64=True) as dst, path.open("rb") as src:
                while chunk := src.read(CHUNK):
                    dst.write(chunk)
                    if data := sink.drain():
                        yield data
    if data := sink.drain():
        yield data


def write_zip(entries: Iterable[tuple[str, Path]], out: Path) -> None:
    with out.open("wb") as fh:
        for chunk in iter_zip(entries):
            fh.write(chunk)
