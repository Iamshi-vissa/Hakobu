from __future__ import annotations

import io
import tarfile
import tempfile
import zipfile
from pathlib import Path

import py7zr
import pytest

from app.config import get_settings
from engines.archive import ArchiveEngine, safe_name
from engines.base import ConversionError
from tests.conftest import convert, detected

ENGINE = ArchiveEngine()
FORMATS = ("zip", "tar", "tar.gz", "7z")
EXPECTED = {"docs/readme.txt": b"hello " * 200, "data/bytes.bin": bytes(range(256)) * 40}


def _contents(path, fmt: str) -> dict[str, bytes]:
    if fmt == "zip":
        with zipfile.ZipFile(path) as archive:
            return {n: archive.read(n) for n in archive.namelist() if not n.endswith("/")}
    if fmt == "7z":
        with tempfile.TemporaryDirectory() as tmp, py7zr.SevenZipFile(path) as archive:
            archive.extractall(path=tmp)
            root = Path(tmp)
            return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with tarfile.open(path) as archive:
        return {m.name: archive.extractfile(m).read() for m in archive.getmembers() if m.isfile()}


@pytest.mark.parametrize(("src", "dst"), [(s, d) for s in FORMATS for d in FORMATS if s != d])
def test_round_trip_preserves_bytes(samples, tmp_path, src: str, dst: str) -> None:
    [out] = convert(ENGINE, samples.get(src), dst, tmp_path)
    assert detected(out) == dst
    assert _contents(out, dst) == EXPECTED


@pytest.mark.parametrize(("raw", "clean"), [("../../etc/passwd", None), ("/abs/file", "abs/file"),
                                            ("a/./b//c", "a/b/c"), ("..", None), ("ok.txt", "ok.txt")])
def test_safe_name(raw: str, clean: str | None) -> None:
    assert safe_name(raw) == clean


def test_zip_slip_entries_are_dropped(tmp_path) -> None:
    src = tmp_path / "slip.zip"
    with zipfile.ZipFile(src, "w") as archive:
        archive.writestr("../../evil.txt", "x")
        archive.writestr("fine.txt", "y")
    [out] = convert(ENGINE, src, "tar", tmp_path)
    with tarfile.open(out) as archive:
        assert archive.getnames() == ["fine.txt"]


def test_tar_links_and_devices_are_skipped(tmp_path) -> None:
    src = tmp_path / "links.tar"
    with tarfile.open(src, "w") as archive:
        link = tarfile.TarInfo("passwd")
        link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
        archive.addfile(link)
        info = tarfile.TarInfo("real.txt")
        info.size = 2
        archive.addfile(info, io.BytesIO(b"ok"))
    [out] = convert(ENGINE, src, "zip", tmp_path)
    assert zipfile.ZipFile(out).namelist() == ["real.txt"]


def test_archive_bomb_is_stopped(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "max_archive_expanded_mb", 1)
    src = tmp_path / "bomb.zip"
    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("zeros.bin", b"\0" * (5 * 1024 * 1024))
    with pytest.raises(ConversionError, match="expands"):
        convert(ENGINE, src, "tar", tmp_path)
