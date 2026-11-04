"""Identifier generation/validation and filename sanitisation."""

from __future__ import annotations

import re
import secrets
import unicodedata

from app.errors import ApiError, ErrorCode

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_UNSAFE_CHARS = re.compile(r"[^\w\s.()\[\]-]", re.UNICODE)
_SPACES = re.compile(r"\s+")
MAX_NAME_LENGTH = 120


def new_id() -> str:
    return secrets.token_urlsafe(16)


def checked_id(value: str, what: str = "item") -> str:
    """Return ``value`` if it is a well-formed id, else raise a 404 ApiError."""
    if not _ID_RE.match(value):
        raise ApiError(404, ErrorCode.NOT_FOUND, f"That {what} doesn't exist or has expired.")
    return value


def sanitize_filename(name: str, fallback: str = "file") -> str:
    """Reduce an untrusted filename to a safe, display-friendly basename."""
    name = unicodedata.normalize("NFKC", name)
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = _SPACES.sub(" ", _UNSAFE_CHARS.sub("_", name)).strip(" .")
    if len(name) > MAX_NAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        keep = MAX_NAME_LENGTH - len(ext) - 1
        name = f"{stem[:keep]}.{ext}" if dot and 0 < len(ext) <= 10 else name[:MAX_NAME_LENGTH]
    return name or fallback


def stem_of(name: str) -> str:
    lower = name.lower()
    if lower.endswith(".tar.gz"):
        return name[:-7] or "file"
    stem, dot, _ = name.rpartition(".")
    return (stem if dot else name) or "file"
