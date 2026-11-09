from __future__ import annotations

import zipfile

import pytest

from engines.document import DocumentEngine, PandocEngine
from tests.conftest import convert, detected, requires

PANDOC = PandocEngine()
OFFICE = DocumentEngine()


@requires("pandoc")
@pytest.mark.parametrize("dst", ["html", "docx", "odt", "rtf", "txt", "epub"])
def test_markdown_via_pandoc(samples, tmp_path, dst: str) -> None:
    [out] = convert(PANDOC, samples.get("md"), dst, tmp_path)
    assert detected(out) == dst


@requires("pandoc")
@pytest.mark.parametrize(("src", "dst"), [("html", "md"), ("docx", "md"), ("docx", "html"), ("odt", "md")])
def test_pandoc_readers(samples, tmp_path, src: str, dst: str) -> None:
    [out] = convert(PANDOC, samples.get(src), dst, tmp_path)
    assert "Hakobu" in out.read_text()


@requires("pandoc")
def test_pandoc_never_embeds_local_files_or_urls(tmp_path) -> None:
    evil = tmp_path / "evil.md"
    evil.write_text("![x](/etc/hostname) ![y](http://169.254.169.254/latest)\n\n<img src='/etc/passwd'>\n")
    [out] = convert(PANDOC, evil, "docx", tmp_path)
    with zipfile.ZipFile(out) as docx:
        assert not [n for n in docx.namelist() if "media" in n]


@requires("soffice")
@pytest.mark.parametrize(
    ("src", "dst"), [("docx", "pdf"), ("odt", "docx"), ("rtf", "odt"), ("txt", "pdf"), ("docx", "doc"), ("html", "pdf")]
)
def test_libreoffice_writer(samples, tmp_path, src: str, dst: str) -> None:
    [out] = convert(OFFICE, samples.get(src), dst, tmp_path)
    assert detected(out) == dst
