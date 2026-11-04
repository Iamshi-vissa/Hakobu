"""PDF tools: render pages, images → PDF, PDF → DOCX/TXT, compress, split and merge."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

import pymupdf

from engines.base import (
    ConversionError,
    ConversionOptions,
    CorruptInputError,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
    run_subprocess,
)

RENDER_TARGETS = ("png", "jpg", "webp")
IMAGE_SOURCES = ("png", "jpg", "webp", "gif", "bmp", "tiff")
DEFAULT_DPI = 150
JPEG_QUALITY = 85


def _noop(_: float) -> None:
    pass


def open_pdf(path: Path) -> pymupdf.Document:
    try:
        doc = pymupdf.open(path)
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise CorruptInputError("This PDF appears to be corrupted.") from exc
    if doc.needs_pass:
        doc.close()
        raise ConversionError("Password-protected PDFs aren't supported.")
    return doc


class PdfEngine(Engine):
    name = "pdf"
    terminal_pairs = frozenset(("pdf", fmt) for fmt in RENDER_TARGETS)
    # Layout reconstruction only makes sense on real PDFs, not ones produced mid-chain.
    entry_only_pairs = frozenset({("pdf", "docx"), ("pdf", "txt")})
    transforms = frozenset({"pdf"})

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs(("pdf",), (*RENDER_TARGETS, "docx", "txt")) | pairs(IMAGE_SOURCES, ("pdf",))

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        src, dst = formats_of(input_path, output_path)
        report = progress or _noop
        if src == dst:
            return _transform(input_path, output_path, options, report)
        if dst in RENDER_TARGETS:
            return _render(input_path, output_path, dst, options, report)
        if dst == "pdf":
            merge_to_pdf([input_path], output_path, report)
        elif dst == "txt":
            _extract_text(input_path, output_path, report)
        else:
            _to_docx(input_path, output_path)
        return [output_path]


def _render(src: Path, out: Path, dst: str, options: ConversionOptions, report: ProgressFn) -> list[Path]:
    from PIL import Image

    outputs = []
    with open_pdf(src) as doc:
        total = doc.page_count
        if total == 0:
            raise CorruptInputError("This PDF has no pages.")
        digits = len(str(total))
        for index, page in enumerate(doc):
            zoom = (options.dpi or DEFAULT_DPI) / 72
            if options.width:
                zoom = options.width / page.rect.width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            target = out if total == 1 else out.with_name(f"{out.stem}-{index + 1:0{digits}d}{out.suffix}")
            if dst == "png":
                pix.save(target)
            else:
                image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                image.save(target, "JPEG" if dst == "jpg" else "WEBP", quality=options.quality or JPEG_QUALITY)
            outputs.append(target)
            report((index + 1) / total)
    return outputs


def merge_to_pdf(inputs: Sequence[Path], out: Path, progress: ProgressFn | None = None) -> None:
    """Concatenate PDFs and images (each image becomes one page) into a single PDF."""
    report = progress or _noop
    with pymupdf.open() as merged:
        for index, path in enumerate(inputs):
            if path.suffix.lower() == ".pdf":
                with open_pdf(path) as doc:
                    merged.insert_pdf(doc)
            else:
                try:
                    with pymupdf.open(path) as image:
                        with pymupdf.open("pdf", image.convert_to_pdf()) as page_pdf:
                            merged.insert_pdf(page_pdf)
                except (pymupdf.FileDataError, RuntimeError) as exc:
                    raise CorruptInputError(f"Could not read image {path.name}.") from exc
            report((index + 1) / len(inputs))
        merged.save(out, garbage=3, deflate=True)


def _extract_text(src: Path, out: Path, report: ProgressFn) -> None:
    with open_pdf(src) as doc, out.open("w", encoding="utf-8") as fh:
        for index, page in enumerate(doc):
            fh.write(page.get_text())
            fh.write("\f")  # form feed between pages, like pdftotext
            report((index + 1) / max(doc.page_count, 1))


def _to_docx(src: Path, out: Path) -> None:
    from pdf2docx import Converter

    open_pdf(src).close()  # validate (corruption / password) with a friendly error first
    converter = Converter(str(src))
    try:
        converter.convert(str(out), multi_processing=False)
    except Exception as exc:  # pdf2docx raises bare exceptions on layout failures
        raise ConversionError("This PDF's layout could not be converted to Word.") from exc
    finally:
        converter.close()


def _transform(src: Path, out: Path, options: ConversionOptions, report: ProgressFn) -> list[Path]:
    current = src
    if options.pdf_compress:
        _compress(src, out)
        current = out
    report(0.5)
    if options.pdf_split:
        outputs = _split(current, out)
    else:
        if current != out:
            shutil.copyfile(current, out)
        outputs = [out]
    report(1.0)
    return outputs


def _compress(src: Path, out: Path) -> None:
    if shutil.which("gs"):
        run_subprocess([
            "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET", "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.5", "-dPDFSETTINGS=/ebook", "-dDetectDuplicateImages=true",
            f"-sOutputFile={out}", src,
        ])
    else:
        with open_pdf(src) as doc:
            doc.save(out, garbage=4, deflate=True, deflate_images=True, clean=True)
    if out.stat().st_size >= src.stat().st_size:
        shutil.copyfile(src, out)  # already optimal; never hand back a bigger file


def _split(src: Path, out: Path) -> list[Path]:
    outputs = []
    with open_pdf(src) as doc:
        digits = len(str(doc.page_count))
        for index in range(doc.page_count):
            target = out.with_name(f"{out.stem}-{index + 1:0{digits}d}.pdf")
            with pymupdf.open() as single:
                single.insert_pdf(doc, from_page=index, to_page=index)
                single.save(target, garbage=3, deflate=True)
            outputs.append(target)
    if out.exists() and out not in outputs:
        out.unlink()
    return outputs
