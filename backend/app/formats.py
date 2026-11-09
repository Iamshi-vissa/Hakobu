"""Catalogue of every format Hakobu knows about."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Category(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    AUDIO = "audio"
    VIDEO = "video"
    EBOOK = "ebook"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class Format:
    id: str
    label: str
    category: Category
    extension: str  # canonical output extension (without dot)
    mime: str
    aliases: tuple[str, ...] = ()  # other extensions that map to this format


_C = Category
FORMATS: dict[str, Format] = {
    f.id: f
    for f in (
        # Images
        Format("png", "PNG", _C.IMAGE, "png", "image/png"),
        Format("jpg", "JPEG", _C.IMAGE, "jpg", "image/jpeg", ("jpeg", "jpe", "jfif")),
        Format("webp", "WebP", _C.IMAGE, "webp", "image/webp"),
        Format("gif", "GIF", _C.IMAGE, "gif", "image/gif"),
        Format("bmp", "BMP", _C.IMAGE, "bmp", "image/bmp"),
        Format("tiff", "TIFF", _C.IMAGE, "tiff", "image/tiff", ("tif",)),
        Format("heic", "HEIC", _C.IMAGE, "heic", "image/heic", ("heif", "hif")),
        Format("avif", "AVIF", _C.IMAGE, "avif", "image/avif"),
        Format("ico", "ICO", _C.IMAGE, "ico", "image/vnd.microsoft.icon"),
        Format("svg", "SVG", _C.IMAGE, "svg", "image/svg+xml"),
        # Documents
        Format("pdf", "PDF", _C.DOCUMENT, "pdf", "application/pdf"),
        Format(
            "docx",
            "Word (DOCX)",
            _C.DOCUMENT,
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        Format("doc", "Word 97 (DOC)", _C.DOCUMENT, "doc", "application/msword"),
        Format("odt", "OpenDocument Text", _C.DOCUMENT, "odt", "application/vnd.oasis.opendocument.text"),
        Format("rtf", "Rich Text", _C.DOCUMENT, "rtf", "application/rtf"),
        Format("txt", "Plain text", _C.DOCUMENT, "txt", "text/plain", ("text", "log")),
        Format("html", "HTML", _C.DOCUMENT, "html", "text/html", ("htm", "xhtml")),
        Format("md", "Markdown", _C.DOCUMENT, "md", "text/markdown", ("markdown",)),
        # Spreadsheets & data
        Format(
            "xlsx",
            "Excel (XLSX)",
            _C.SPREADSHEET,
            "xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        Format("xls", "Excel 97 (XLS)", _C.SPREADSHEET, "xls", "application/vnd.ms-excel"),
        Format("ods", "OpenDocument Sheet", _C.SPREADSHEET, "ods", "application/vnd.oasis.opendocument.spreadsheet"),
        Format("csv", "CSV", _C.SPREADSHEET, "csv", "text/csv"),
        Format("tsv", "TSV", _C.SPREADSHEET, "tsv", "text/tab-separated-values", ("tab",)),
        Format("json", "JSON", _C.SPREADSHEET, "json", "application/json"),
        Format("xml", "XML", _C.SPREADSHEET, "xml", "application/xml"),
        Format("yaml", "YAML", _C.SPREADSHEET, "yaml", "application/yaml", ("yml",)),
        # Presentations
        Format(
            "pptx",
            "PowerPoint (PPTX)",
            _C.PRESENTATION,
            "pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        Format("ppt", "PowerPoint 97 (PPT)", _C.PRESENTATION, "ppt", "application/vnd.ms-powerpoint"),
        Format("odp", "OpenDocument Slides", _C.PRESENTATION, "odp", "application/vnd.oasis.opendocument.presentation"),
        # Audio
        Format("mp3", "MP3", _C.AUDIO, "mp3", "audio/mpeg"),
        Format("wav", "WAV", _C.AUDIO, "wav", "audio/wav"),
        Format("aac", "AAC", _C.AUDIO, "aac", "audio/aac"),
        Format("m4a", "M4A", _C.AUDIO, "m4a", "audio/mp4"),
        Format("ogg", "Ogg Vorbis", _C.AUDIO, "ogg", "audio/ogg", ("oga",)),
        Format("flac", "FLAC", _C.AUDIO, "flac", "audio/flac"),
        Format("opus", "Opus", _C.AUDIO, "opus", "audio/opus"),
        # Video
        Format("mp4", "MP4", _C.VIDEO, "mp4", "video/mp4", ("m4v",)),
        Format("mov", "QuickTime (MOV)", _C.VIDEO, "mov", "video/quicktime"),
        Format("mkv", "Matroska (MKV)", _C.VIDEO, "mkv", "video/x-matroska"),
        Format("webm", "WebM", _C.VIDEO, "webm", "video/webm"),
        Format("avi", "AVI", _C.VIDEO, "avi", "video/x-msvideo"),
        # E-books
        Format("epub", "EPUB", _C.EBOOK, "epub", "application/epub+zip"),
        Format("mobi", "MOBI", _C.EBOOK, "mobi", "application/x-mobipocket-ebook"),
        Format("azw3", "Kindle (AZW3)", _C.EBOOK, "azw3", "application/vnd.amazon.ebook", ("azw",)),
        # Archives
        Format("zip", "ZIP", _C.ARCHIVE, "zip", "application/zip"),
        Format("tar", "TAR", _C.ARCHIVE, "tar", "application/x-tar"),
        Format("tar.gz", "TAR.GZ", _C.ARCHIVE, "tar.gz", "application/gzip", ("tgz",)),
        Format("7z", "7-Zip", _C.ARCHIVE, "7z", "application/x-7z-compressed"),
    )
}

# Extension (lower-case, no dot) -> format id.
EXTENSION_MAP: dict[str, str] = {ext: f.id for f in FORMATS.values() for ext in (f.extension, *f.aliases)}

# Global popularity used to order targets ("most likely choices first").
POPULARITY: tuple[str, ...] = (
    "pdf",
    "jpg",
    "png",
    "webp",
    "docx",
    "mp4",
    "mp3",
    "xlsx",
    "csv",
    "zip",
    "gif",
    "txt",
    "md",
    "html",
    "epub",
    "wav",
    "m4a",
    "json",
    "avif",
    "pptx",
    "heic",
    "mov",
    "webm",
    "flac",
    "ogg",
    "opus",
    "aac",
    "mkv",
    "odt",
    "ods",
    "odp",
    "rtf",
    "tiff",
    "bmp",
    "ico",
    "yaml",
    "xml",
    "tsv",
    "tar.gz",
    "7z",
    "tar",
    "mobi",
    "azw3",
    "doc",
    "xls",
    "ppt",
    "avi",
    "svg",
)
POPULARITY_RANK: dict[str, int] = {fmt: i for i, fmt in enumerate(POPULARITY)}


def extension_of(filename: str) -> str | None:
    """Return the format id implied by a filename's extension, if any."""
    name = filename.lower()
    if name.endswith(".tar.gz"):
        return "tar.gz"
    _, dot, ext = name.rpartition(".")
    return EXTENSION_MAP.get(ext) if dot else None
