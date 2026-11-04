"""Format detection from leading bytes (extension only used to break text ties)."""

from __future__ import annotations

import pytest

from app.detection import HEAD_SIZE, detect
from tests.conftest import requires

BINARY = ["png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico", "pdf", "rtf",
          "docx", "odt", "epub", "xlsx", "pptx", "zip", "tar", "tar.gz", "7z", "wav"]


@pytest.mark.parametrize("fmt", BINARY)
def test_binary_formats_ignore_the_extension(samples, fmt: str) -> None:
    head = samples.get(fmt).read_bytes()[:HEAD_SIZE]
    assert detect(head, "upload.bin").format == fmt


@requires("ffmpeg")
@pytest.mark.parametrize("fmt", ["mp3", "mp4"])
def test_media_formats(samples, fmt: str) -> None:
    assert detect(samples.get(fmt).read_bytes()[:HEAD_SIZE], "x.bin").format == fmt


@requires("soffice")
@pytest.mark.parametrize("fmt", ["doc", "xls", "ppt", "ods", "odp"])
def test_office_containers(samples, fmt: str) -> None:
    data = samples.get(fmt).read_bytes()
    read_at = lambda offset, n: data[offset:offset + n]  # noqa: E731
    assert detect(data[:HEAD_SIZE], "x.bin", read_at=read_at).format == fmt


def test_misleading_extension_is_overridden(samples) -> None:
    assert detect(samples.get("png").read_bytes()[:HEAD_SIZE], "photo.jpg").format == "png"


@pytest.mark.parametrize(("fmt", "name"), [
    ("md", "notes.md"), ("csv", "data.csv"), ("tsv", "data.tsv"), ("json", "data.json"),
    ("yaml", "data.yml"), ("xml", "data.xml"), ("html", "page.html"), ("svg", "logo.svg"), ("txt", "a.txt"),
])
def test_text_formats_with_hint(samples, fmt: str, name: str) -> None:
    assert detect(samples.get(fmt).read_bytes(), name).format == fmt


@pytest.mark.parametrize(("content", "expected"), [
    (b'{"a": 1}', "json"),
    (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "svg"),
    (b"<!DOCTYPE html><html></html>", "html"),
    (b"a,b,c\n1,2,3\n4,5,6\n", "csv"),
    (b"a\tb\n1\t2\n", "tsv"),
    (b"# Title\n\nSome text\n", "md"),
    (b"key: value\nother: 2\n", "yaml"),
    (b"just some words\n", "txt"),
])
def test_text_heuristics_without_hint(content: bytes, expected: str) -> None:
    assert detect(content, "upload").format == expected


def test_json_hint_rejected_for_non_json_content() -> None:
    assert detect(b"<root/>", "data.json").format == "xml"


@pytest.mark.parametrize("content", [
    b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64,
    b"\x7fELF" + b"\x00" * 100,  # libmagic calls this text/plain; it must still be rejected
    b"MZ\x90\x00" + b"\x00" * 64,
    b"\xcf\xfa\xed\xfe" + b"\x00" * 64,
    b"\x00\x01\x02binary junk" * 10,
])
def test_executables_are_unsupported(content: bytes) -> None:
    assert detect(content, "innocent.png").format is None
