"""Storage abstraction, cleanup, filename sanitising and the streaming ZIP writer."""

from __future__ import annotations

import asyncio
import os
import time
import zipfile
from pathlib import Path

import pytest

from app.errors import ApiError
from app.naming import checked_id, new_id, sanitize_filename, stem_of
from app.storage import LocalStorage, StorageLimitExceeded
from app.zipstream import unique_names, write_zip


async def _chunks(*parts: bytes):
    for part in parts:
        yield part


def test_append_read_move_and_limits(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    assert asyncio.run(storage.append("incoming/a", _chunks(b"abc", b"def"), 100)) == 6
    assert asyncio.run(storage.append("incoming/a", _chunks(b"gh"), 100)) == 8
    assert storage.read_range("incoming/a", 0, 4) == b"abcd"
    storage.move("incoming/a", "uploads/x/source.txt")
    assert storage.size("uploads/x/source.txt") == 8 and not storage.exists("incoming/a")
    with pytest.raises(StorageLimitExceeded):
        asyncio.run(storage.append("incoming/b", _chunks(b"x" * 10), 5))


def test_keys_cannot_escape_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        LocalStorage(tmp_path).exists("../etc/passwd")


def test_write_path_commits_only_on_success(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    with pytest.raises(RuntimeError), storage.write_path("outputs/j/file.txt") as path:
        path.write_text("partial")
        raise RuntimeError
    assert not storage.exists("outputs/j/file.txt")
    assert list((tmp_path / "outputs" / "j").iterdir()) == []


def test_purge_removes_only_expired_entries(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    old, fresh = tmp_path / "uploads" / "old", tmp_path / "uploads" / "fresh"
    for d in (old, fresh):
        d.mkdir(parents=True)
        (d / "source.png").write_bytes(b"x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    assert storage.purge_older_than(3600) == 1
    assert not old.exists() and fresh.exists()


@pytest.mark.parametrize(("raw", "clean"), [
    ("../../etc/passwd", "passwd"),
    ("C:\\Users\\me\\photo.png", "photo.png"),
    ("report<script>.pdf", "report_script_.pdf"),
    ("\x00\x1fname.txt", "name.txt"),
    ("...", "file"),
    ("写真 2024.jpg", "写真 2024.jpg"),
])
def test_sanitize_filename(raw: str, clean: str) -> None:
    assert sanitize_filename(raw) == clean


def test_long_names_keep_extension() -> None:
    name = sanitize_filename("a" * 300 + ".docx")
    assert len(name) <= 120 and name.endswith(".docx")


def test_ids() -> None:
    assert checked_id(new_id()) and stem_of("archive.tar.gz") == "archive" and stem_of("x") == "x"
    with pytest.raises(ApiError):
        checked_id("../../secret")


def test_streaming_zip(tmp_path: Path) -> None:
    a, b = tmp_path / "a.txt", tmp_path / "b.png"
    a.write_text("hello" * 1000)
    b.write_bytes(os.urandom(5000))
    names = unique_names(["x.txt", "x.txt"])
    assert names == ["x.txt", "x (2).txt"]
    out = tmp_path / "out.zip"
    write_zip([(names[0], a), ("pic.png", b)], out)
    with zipfile.ZipFile(out) as archive:
        assert archive.testzip() is None
        assert archive.read("x.txt") == a.read_bytes()
        assert archive.getinfo("pic.png").compress_type == zipfile.ZIP_STORED
