"""Content-based format detection.

Only the first :data:`HEAD_SIZE` bytes of a file are inspected. Binary formats are
identified from their signatures; container formats (ZIP, OLE2, ISO-BMFF, Matroska)
are disambiguated from markers inside that head. Text formats fall back to the file
extension when the content is compatible, then to light heuristics. python-magic is
used to report a MIME type and as a last-resort fallback.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Callable
from dataclasses import dataclass

import magic

from app.formats import FORMATS, extension_of

HEAD_SIZE = 64 * 1024
OLE_DIRECTORY_READ = 2048  # first few directory sectors of an OLE2 compound file

ReadAt = Callable[[int, int], bytes]
"""Optional ``(offset, n) -> bytes`` for formats whose marker sits at a known offset."""

_TEXT_FORMATS = frozenset({"txt", "md", "csv", "tsv", "json", "yaml", "xml", "html", "svg"})
_OOXML = {b"word/": "docx", b"xl/": "xlsx", b"ppt/": "pptx"}
_ODF_EPUB = {
    b"application/epub+zip": "epub",
    b"application/vnd.oasis.opendocument.text": "odt",
    b"application/vnd.oasis.opendocument.spreadsheet": "ods",
    b"application/vnd.oasis.opendocument.presentation": "odp",
}
_OLE_STREAMS = {
    "WordDocument".encode("utf-16-le"): "doc",
    "Workbook".encode("utf-16-le"): "xls",
    "Book".encode("utf-16-le"): "xls",
    "PowerPoint Document".encode("utf-16-le"): "ppt",
}
_FTYP_BRANDS = {
    b"heic": "heic", b"heix": "heic", b"hevc": "heic", b"heim": "heic", b"heis": "heic",
    b"hevx": "heic", b"mif1": "heic", b"msf1": "heic",
    b"avif": "avif", b"avis": "avif",
    b"M4A ": "m4a", b"M4B ": "m4a", b"M4P ": "m4a",
    b"qt  ": "mov",
}
_MIME_FALLBACK = {f.mime: f.id for f in FORMATS.values()}
# ELF, PE (MZ), Mach-O (32/64-bit, both endians) and fat binaries are never accepted.
_EXECUTABLE_MAGIC = (b"\x7fELF", b"MZ", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
                     b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")


@dataclass(frozen=True, slots=True)
class Detection:
    format: str | None
    mime: str


def detect(head: bytes, filename: str = "", read_at: ReadAt | None = None) -> Detection:
    """Detect a file's format from its leading bytes (and, for text, its name).

    ``read_at`` lets OLE2 files (DOC/XLS/PPT), whose stream directory may sit anywhere,
    be classified by reading just that directory sector instead of the whole file.
    """
    hint = extension_of(filename)
    mime = magic.from_buffer(head, mime=True) if head else "application/x-empty"
    text = _is_text(head)
    if not text and head.startswith(_EXECUTABLE_MAGIC):
        return Detection(None, mime)
    fmt = _detect_binary(head, hint, read_at)
    if fmt is None and text:
        fmt = _detect_text(head, hint)
    if fmt is None and (text or not mime.startswith("text/")):
        fmt = _MIME_FALLBACK.get(mime)
    if fmt is not None:
        mime = FORMATS[fmt].mime
    return Detection(fmt, mime)


def _detect_binary(h: bytes, hint: str | None, read_at: ReadAt | None) -> str | None:
    if h.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if h.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if h[:4] == b"RIFF" and len(h) >= 12:
        return {b"WEBP": "webp", b"WAVE": "wav", b"AVI ": "avi"}.get(h[8:12])
    if h[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if h.startswith(b"BM") and len(h) >= 14 and int.from_bytes(h[6:10], "little") == 0:
        return "bmp"
    if h.startswith(b"\x00\x00\x01\x00") and len(h) >= 6 and h[4:6] != b"\x00\x00":
        return "ico"
    if b"%PDF-" in h[:1024]:
        return "pdf"
    if h.startswith(b"{\\rtf"):
        return "rtf"
    if h.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    if h.startswith(b"\x1f\x8b"):
        return "tar.gz" if _gzip_contains_tar(h) else None
    if len(h) > 262 and h[257:262] == b"ustar":
        return "tar"
    if h.startswith(b"fLaC"):
        return "flac"
    if h.startswith(b"OggS"):
        return "opus" if b"OpusHead" in h[:512] else "ogg"
    if h.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm" if b"webm" in h[:4096] else "mkv"
    if len(h) >= 12 and h[4:8] == b"ftyp":
        return _detect_ftyp(h, hint)
    if len(h) >= 68 and h[60:68] == b"BOOKMOBI":
        return "azw3" if hint == "azw3" else "mobi"
    if h.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        return _detect_zip(h, hint)
    if h.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return _detect_ole(h, hint, read_at)
    if h.startswith(b"ID3"):
        return "aac" if hint == "aac" else "mp3"
    if len(h) >= 2 and h[0] == 0xFF:
        if h[1] & 0xF6 == 0xF0:  # ADTS sync, layer bits 00
            return "aac"
        if h[1] & 0xE0 == 0xE0 and (h[1] >> 1) & 0x3:  # MPEG audio frame sync
            return "mp3"
    return None


def _detect_ftyp(h: bytes, hint: str | None) -> str:
    box_size = int.from_bytes(h[:4], "big")
    major = h[8:12]
    compatible = [h[i:i + 4] for i in range(16, min(box_size, len(h), 64), 4)]
    # AVIF files usually use the generic "mif1" major brand with "avif" as compatible brand.
    if b"avif" in compatible or b"avis" in compatible:
        return "avif"
    if major in _FTYP_BRANDS:
        return _FTYP_BRANDS[major]
    # Generic ISO brands are shared by MP4 video and M4A audio; trust the hint for audio.
    return "m4a" if hint == "m4a" else ("mov" if hint == "mov" else "mp4")


def _detect_zip(h: bytes, hint: str | None) -> str:
    for marker, fmt in _ODF_EPUB.items():
        if marker in h[:256]:
            return fmt
    for marker, fmt in _OOXML.items():
        if marker in h:
            return fmt
    if b"[Content_Types].xml" in h and hint in ("docx", "xlsx", "pptx"):
        return hint
    return "zip"


def _detect_ole(h: bytes, hint: str | None, read_at: ReadAt | None) -> str:
    if hint in ("doc", "xls", "ppt"):
        return hint
    regions = [h]
    if read_at is not None and len(h) >= 52:
        sector_size = 1 << int.from_bytes(h[30:32], "little")
        directory = int.from_bytes(h[48:52], "little")
        if sector_size in (512, 4096) and directory < 0xFFFFFFFA:
            regions.append(read_at((directory + 1) * sector_size, OLE_DIRECTORY_READ))
    for region in regions:
        for marker, fmt in _OLE_STREAMS.items():
            if marker in region:
                return fmt
    return "doc"


def _gzip_contains_tar(h: bytes) -> bool:
    try:
        inflated = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(h, 1024)
    except zlib.error:
        return False
    return len(inflated) > 262 and inflated[257:262] == b"ustar"


def _is_text(h: bytes) -> bool:
    if not h or b"\x00" in h[:8192]:
        return False
    sample = h[:8192]
    # Trim a possibly truncated trailing UTF-8 sequence.
    for cut in range(4):
        try:
            (sample[: len(sample) - cut] if cut else sample).decode("utf-8")
            return True
        except UnicodeDecodeError:
            continue
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in sample)
    return printable / len(sample) > 0.95


_YAML_LINE = re.compile(r"^[\w\"'-][^:\n]*:(\s|$)")
_MD_LINE = re.compile(r"^(#{1,6}\s|[-*+]\s|\d+\.\s|```|>\s|\[.+\]\(.+\))")


def _detect_text(h: bytes, hint: str | None) -> str:
    text = h[:8192].decode("utf-8", errors="ignore").lstrip("﻿")
    lead = text.lstrip().lower()
    if lead.startswith("<svg") or (lead.startswith("<?xml") and "<svg" in lead[:2048]):
        return "svg"
    if lead.startswith(("<!doctype html", "<html")):
        return "html"
    starts_markup = lead.startswith("<")
    starts_json = lead.startswith(("{", "["))
    if hint in _TEXT_FORMATS and hint != "svg":
        compatible = {
            "json": starts_json,
            "xml": starts_markup,
            "html": starts_markup,
        }.get(hint, not starts_markup or hint in ("md", "txt"))
        if compatible:
            return hint
    if starts_markup:
        return "html" if re.search(r"<(head|body|div|p)[\s>]", lead[:4096]) else "xml"
    if starts_json:
        return "json"
    lines = [ln for ln in text.splitlines()[:20] if ln.strip()]
    if not lines:
        return "txt"
    head_lines = lines[:5]
    if lines[0].strip() == "---" or (
        any(_YAML_LINE.match(ln) for ln in head_lines)
        and all(_YAML_LINE.match(ln) or ln.startswith((" ", "- ")) for ln in head_lines)
    ):
        return "yaml"
    for sep, fmt in (("\t", "tsv"), (",", "csv")):
        counts = {ln.count(sep) for ln in lines[:10]}
        if len(counts) == 1 and counts.pop() > 0 and len(lines) > 1:
            return fmt
    if any(_MD_LINE.match(ln) for ln in lines):
        return "md"
    return "txt"
