from __future__ import annotations

import pymupdf
import pytest

from engines.base import CorruptInputError
from engines.pdf import PdfEngine, merge_to_pdf
from tests.conftest import convert, detected

ENGINE = PdfEngine()


@pytest.mark.parametrize("dst", ["png", "jpg", "webp"])
def test_render_one_image_per_page(samples, tmp_path, dst: str) -> None:
    outputs = convert(ENGINE, samples.get("pdf"), dst, tmp_path, dpi=72)
    assert [p.name for p in outputs] == [f"out-1.{dst}", f"out-2.{dst}"]
    assert all(detected(p) == dst for p in outputs)


def test_render_width(samples, tmp_path) -> None:
    from PIL import Image

    outputs = convert(ENGINE, samples.get("pdf"), "png", tmp_path, width=300)
    assert Image.open(outputs[0]).width == 300


def test_pdf_to_text(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("pdf"), "txt", tmp_path)
    assert "Hakobu test page 2" in out.read_text()


def test_pdf_to_docx(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("pdf"), "docx", tmp_path)
    assert detected(out) == "docx"


@pytest.mark.parametrize("src", ["png", "jpg", "tiff"])
def test_image_to_pdf(samples, tmp_path, src: str) -> None:
    [out] = convert(ENGINE, samples.get(src), "pdf", tmp_path)
    assert pymupdf.open(out).page_count == 1


def test_split_and_compress(samples, tmp_path) -> None:
    outputs = convert(ENGINE, samples.get("pdf"), "pdf", tmp_path, pdf_split=True, pdf_compress=True)
    assert [pymupdf.open(p).page_count for p in outputs] == [1, 1]


def test_compress_never_grows(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("pdf"), "pdf", tmp_path, pdf_compress=True)
    assert out.stat().st_size <= samples.get("pdf").stat().st_size


def test_merge(samples, tmp_path) -> None:
    out = tmp_path / "merged.pdf"
    merge_to_pdf([samples.get("pdf"), samples.get("png"), samples.get("pdf")], out)
    assert pymupdf.open(out).page_count == 5


def test_corrupted_pdf(tmp_path) -> None:
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"%PDF-1.7\n garbage")
    with pytest.raises(CorruptInputError):
        convert(ENGINE, bad, "png", tmp_path)
