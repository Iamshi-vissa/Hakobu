"""Shared fixtures: isolated settings/Redis/storage and a factory of real sample files."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

# Configure before any app module reads settings.
_DATA_DIR = Path(tempfile.mkdtemp(prefix="hakobu-test-"))
os.environ.update({
    "HAKOBU_DATA_DIR": str(_DATA_DIR),
    "HAKOBU_SYNC_JOBS": "1",
    "HAKOBU_RATE_LIMIT_PER_MINUTE": "10000",
    "HAKOBU_UNOSERVER_INSTANCES": "0",
    "HAKOBU_FFMPEG_HWACCEL": "off",
})

import fakeredis  # noqa: E402
import fakeredis.aioredis  # noqa: E402

from app.redis_client import set_clients  # noqa: E402


def has(tool: str) -> bool:
    return shutil.which(tool) is not None


def requires(*tools: str) -> pytest.MarkDecorator:
    missing = [t for t in tools if not has(t)]
    return pytest.mark.skipif(bool(missing), reason=f"missing tool(s): {', '.join(missing)}")


@pytest.fixture(autouse=True)
def fake_redis() -> Iterator[None]:
    server = fakeredis.FakeServer()
    set_clients(fakeredis.FakeRedis(server=server),
                fakeredis.aioredis.FakeRedis(server=server, decode_responses=True))
    yield


@pytest.fixture
def client() -> Iterator:
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------- sample files ----------

def _run(*args: str | Path) -> None:
    subprocess.run([str(a) for a in args], check=True, capture_output=True, timeout=180)


def _pdf(path: Path) -> None:
    import pymupdf

    with pymupdf.open() as doc:
        for number in (1, 2):
            page = doc.new_page()
            page.insert_text((72, 72), f"Hakobu test page {number}", fontsize=18)
        doc.save(path)


def _image(fmt: str) -> Callable[[Path], None]:
    def build(path: Path) -> None:
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (320, 200), (79, 70, 229, 255))
        ImageDraw.Draw(image).ellipse((40, 40, 160, 160), fill=(34, 211, 238, 200))
        if fmt == "gif":
            frames = [image.convert("P"), Image.new("RGB", (320, 200), (168, 85, 247)).convert("P")]
            frames[0].save(path, save_all=True, append_images=frames[1:], duration=200, loop=0)
            return
        if fmt in ("jpg", "bmp"):
            image = image.convert("RGB")
        if fmt == "heic":
            import pillow_heif

            pillow_heif.register_heif_opener()
        image.save(path, {"jpg": "JPEG", "heic": "HEIF"}.get(fmt, fmt.upper()))

    return build


def _xlsx(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["name", "age", "city"])
    sheet.append(["Ada", 36, "London"])
    sheet.append(["Linus", 28, "Helsinki"])
    workbook.save(path)


def _pptx(path: Path) -> None:
    from pptx import Presentation

    deck = Presentation()
    for title in ("Hakobu", "Second slide"):
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.shapes.title.text = title
    deck.save(path)


MARKDOWN = "# Hakobu\n\nCarry your files *anywhere*.\n\n- one\n- two\n"
CSV = "name,age,city\nAda,36,London\nLinus,28,Helsinki\n\"Smith, J\",,Paris\n"


class Samples:
    """Builds each sample format once per session, deriving some from others."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.builders: dict[str, Callable[[Path], None]] = {
            **{fmt: _image(fmt) for fmt in ("png", "jpg", "webp", "gif", "bmp", "tiff", "heic", "avif", "ico")},
            "svg": lambda p: p.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60">'
                                          '<rect width="120" height="60" fill="teal"/></svg>'),
            "md": lambda p: p.write_text(MARKDOWN),
            "txt": lambda p: p.write_text("Plain text from Hakobu.\nSecond line.\n"),
            "html": lambda p: p.write_text("<!doctype html><html><body><h1>Hakobu</h1><p>Hello</p></body></html>"),
            "rtf": lambda p: p.write_text(r"{\rtf1\ansi{\fonttbl\f0\fswiss Helvetica;}\f0\pard Hakobu RTF.\par}"),
            "docx": lambda p: _run("pandoc", "-f", "gfm", "-o", p, self.get("md")),
            "odt": lambda p: _run("pandoc", "-f", "gfm", "-o", p, self.get("md")),
            "epub": lambda p: _run("pandoc", "-f", "gfm", "-s", "--metadata", "title=Hakobu", "-o", p, self.get("md")),
            "pdf": _pdf,
            "csv": lambda p: p.write_text(CSV),
            "tsv": lambda p: p.write_text(CSV.replace(",", "\t").replace('"Smith\t J"', "Smith, J")),
            "json": lambda p: p.write_text('[{"name": "Ada", "age": 36}, {"name": "Linus", "age": 28}]'),
            "yaml": lambda p: p.write_text("- name: Ada\n  age: 36\n- name: Linus\n  age: 28\n"),
            "xml": lambda p: p.write_text("<people><person><name>Ada</name><age>36</age></person>"
                                          "<person><name>Linus</name><age>28</age></person></people>"),
            "xlsx": _xlsx,
            "pptx": _pptx,
            "doc": lambda p: self._office(self.get("docx"), p),
            "xls": lambda p: self._office(self.get("xlsx"), p),
            "ods": lambda p: self._office(self.get("xlsx"), p),
            "odp": lambda p: self._office(self.get("pptx"), p),
            "ppt": lambda p: self._office(self.get("pptx"), p),
            "wav": lambda p: _run("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", p),
            "mp3": lambda p: _run("ffmpeg", "-v", "error", "-i", self.get("wav"), "-c:a", "libmp3lame", p),
            "mp4": lambda p: _run(
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=15:duration=2",
                "-f", "lavfi", "-i", "sine=duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", p),
            "mobi": lambda p: _run("ebook-convert", self.get("epub"), p),
            "zip": self._zip,
            "tar": lambda p: self._tar(p, "w"),
            "tar.gz": lambda p: self._tar(p, "w:gz"),
            "7z": self._7z,
        }

    def get(self, fmt: str) -> Path:
        path = self.root / f"sample.{fmt}"
        if not path.exists():
            self.builders[fmt](path)
        return path

    def _office(self, src: Path, out: Path) -> None:
        from engines.office import convert_with_office

        convert_with_office(src, out, out.suffix.lstrip("."))

    @staticmethod
    def _members() -> dict[str, bytes]:
        return {"docs/readme.txt": b"hello " * 200, "data/bytes.bin": bytes(range(256)) * 40}

    def _zip(self, path: Path) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in self._members().items():
                archive.writestr(name, data)

    def _tar(self, path: Path, mode: str) -> None:
        import io

        with tarfile.open(path, mode) as archive:
            for name, data in self._members().items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    def _7z(self, path: Path) -> None:
        import py7zr

        with tempfile.TemporaryDirectory() as tmp, py7zr.SevenZipFile(path, "w") as archive:
            for name, data in self._members().items():
                file = Path(tmp) / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
                archive.write(file, name)


@pytest.fixture(scope="session")
def samples(tmp_path_factory: pytest.TempPathFactory) -> Samples:
    return Samples(tmp_path_factory.mktemp("samples"))


def detected(path: Path) -> str | None:
    from app.detection import HEAD_SIZE, detect

    with path.open("rb") as fh:
        return detect(fh.read(HEAD_SIZE), path.name).format


def convert(engine, src: Path, dst: str, tmp_path: Path, **options) -> list[Path]:
    """Run one engine step into ``tmp_path`` and return the produced files."""
    from app.formats import FORMATS
    from engines.base import ConversionOptions

    out = tmp_path / f"out.{FORMATS[dst].extension}"
    produced = engine.convert(src, out, ConversionOptions(**options))
    assert produced, "engine produced nothing"
    for path in produced:
        assert path.exists() and path.stat().st_size > 0
    return produced
