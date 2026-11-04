"""Archives: ZIP, TAR, TAR.GZ and 7z, converted entry by entry.

Readers push entries into a writer one at a time, so nothing is extracted wholesale:
ZIP and TAR members are streamed straight across; 7z members (and 7z targets, whose
writer needs a sized file) are spooled to a temporary file one entry at a time.
Entry names are sanitised (no absolute paths or ``..``), links and devices are
skipped, and the total expanded size / entry count are capped to defuse archive bombs.
"""

from __future__ import annotations

import posixpath
import shutil
import tarfile
import tempfile
import threading
import time
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import IO, BinaryIO

from app.config import get_settings
from engines.base import (
    ConversionError,
    ConversionOptions,
    CorruptInputError,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
)

ARCHIVES = ("zip", "tar", "tar.gz", "7z")
CHUNK = 1024 * 1024
ZIP_EPOCH = 315_619_200  # 1980-01-02: ZIP can't store earlier timestamps


def _zip_time(mtime: float) -> tuple[int, int, int, int, int, int]:
    return time.localtime(max(mtime, ZIP_EPOCH))[:6]  # type: ignore[return-value]


def safe_name(name: str) -> str | None:
    """Normalise an entry name; None if it would escape the archive root."""
    name = name.replace("\\", "/")
    parts = [p for p in posixpath.normpath(name).split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


class Budget:
    """Tracks expanded bytes and entry count against the configured limits."""

    def __init__(self) -> None:
        settings = get_settings()
        self.max_bytes = settings.max_archive_expanded_mb * 1024 * 1024
        self.max_entries = settings.max_archive_entries
        self.bytes = 0
        self.entries = 0

    def entry(self) -> None:
        self.entries += 1
        if self.entries > self.max_entries:
            raise ConversionError(f"Archives may contain at most {self.max_entries} entries.")

    def consume(self, n: int) -> None:
        self.bytes += n
        if self.bytes > self.max_bytes:
            raise ConversionError("This archive expands to more data than Hakobu allows.")


class _Metered:
    """Read-through wrapper that charges every byte read to the budget."""

    def __init__(self, raw: IO[bytes], budget: Budget) -> None:
        self.raw, self.budget = raw, budget

    def read(self, n: int = -1) -> bytes:
        data = self.raw.read(n)
        self.budget.consume(len(data))
        return data


# ---------- writers ----------

class ArchiveWriter(ABC):
    def __init__(self, out: Path) -> None:
        self.out = out
        self._lock = threading.Lock()  # 7z extraction may deliver entries from worker threads

    def add_file(self, name: str, stream: BinaryIO | _Metered, size: int, mtime: float) -> None:
        with self._lock:
            self._add_file(name, stream, size, mtime)

    def add_dir(self, name: str, mtime: float) -> None:
        with self._lock:
            self._add_dir(name, mtime)

    @abstractmethod
    def _add_file(self, name: str, stream: BinaryIO | _Metered, size: int, mtime: float) -> None: ...

    @abstractmethod
    def _add_dir(self, name: str, mtime: float) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class ZipWriter(ArchiveWriter):
    def __init__(self, out: Path) -> None:
        super().__init__(out)
        self.zip = zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6)

    def _add_file(self, name: str, stream: BinaryIO | _Metered, size: int, mtime: float) -> None:
        info = zipfile.ZipInfo(name, _zip_time(mtime))
        info.compress_type = zipfile.ZIP_DEFLATED
        with self.zip.open(info, "w", force_zip64=True) as dst:
            shutil.copyfileobj(stream, dst, CHUNK)

    def _add_dir(self, name: str, mtime: float) -> None:
        self.zip.writestr(zipfile.ZipInfo(f"{name}/", _zip_time(mtime)), b"")

    def close(self) -> None:
        self.zip.close()


class TarWriter(ArchiveWriter):
    def __init__(self, out: Path, gzip: bool) -> None:
        super().__init__(out)
        self.tar = tarfile.open(out, "w:gz" if gzip else "w", format=tarfile.PAX_FORMAT)  # noqa: SIM115 - closed in close()

    def _add_file(self, name: str, stream: BinaryIO | _Metered, size: int, mtime: float) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mtime, info.mode = size, int(mtime), 0o644
        self.tar.addfile(info, stream)  # type: ignore[arg-type] - only .read() is used

    def _add_dir(self, name: str, mtime: float) -> None:
        info = tarfile.TarInfo(name)
        info.type, info.mtime, info.mode = tarfile.DIRTYPE, int(mtime), 0o755
        self.tar.addfile(info)

    def close(self) -> None:
        self.tar.close()


class SevenZipWriter(ArchiveWriter):
    def __init__(self, out: Path) -> None:
        import py7zr

        super().__init__(out)
        self.archive = py7zr.SevenZipFile(out, "w")
        self.spool = Path(tempfile.mkdtemp(prefix="hakobu-7z-"))

    def _add_file(self, name: str, stream: BinaryIO | _Metered, size: int, mtime: float) -> None:
        spooled = self.spool / "entry"
        with spooled.open("wb") as fh:
            shutil.copyfileobj(stream, fh, CHUNK)
        self.archive.write(spooled, name)
        spooled.unlink()

    def _add_dir(self, name: str, mtime: float) -> None:
        directory = self.spool / "dir"
        directory.mkdir(exist_ok=True)
        self.archive.write(directory, name)

    def close(self) -> None:
        try:
            self.archive.close()
        finally:
            shutil.rmtree(self.spool, ignore_errors=True)


def open_writer(fmt: str, out: Path) -> ArchiveWriter:
    if fmt == "zip":
        return ZipWriter(out)
    if fmt in ("tar", "tar.gz"):
        return TarWriter(out, gzip=fmt == "tar.gz")
    return SevenZipWriter(out)


# ---------- readers ----------

def _copy_zip(path: Path, writer: ArchiveWriter, budget: Budget) -> None:
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            name = safe_name(info.filename)
            if name is None:
                continue
            budget.entry()
            mtime = time.mktime((*info.date_time, 0, 0, -1))
            if info.is_dir():
                writer.add_dir(name, mtime)
                continue
            with archive.open(info) as member:
                writer.add_file(name, _Metered(member, budget), info.file_size, mtime)


def _copy_tar(path: Path, writer: ArchiveWriter, budget: Budget) -> None:
    with tarfile.open(path, "r|*") as archive:  # sequential streaming mode
        for member in archive:
            name = safe_name(member.name)
            if name is None or not (member.isfile() or member.isdir()):
                continue  # skip escapes, links, devices
            budget.entry()
            if member.isdir():
                writer.add_dir(name, member.mtime)
                continue
            stream = archive.extractfile(member)
            if stream is not None:
                writer.add_file(name, _Metered(stream, budget), member.size, member.mtime)


def _copy_7z(path: Path, writer: ArchiveWriter, budget: Budget) -> None:
    import py7zr
    from py7zr.io import Py7zIO, WriterFactory

    spool = Path(tempfile.mkdtemp(prefix="hakobu-7z-"))
    counter = iter(range(1 << 62))

    class SpoolIO(Py7zIO):
        """Receives one decompressed member, then hands it to the writer on close."""

        def __init__(self, name: str, mtime: float) -> None:
            self.name, self.mtime = name, mtime
            self.path = spool / f"{next(counter)}"
            self.fh = self.path.open("w+b")

        def write(self, s: bytes | bytearray) -> int:
            budget.consume(len(s))
            return self.fh.write(s)

        def read(self, size: int | None = None) -> bytes:
            return self.fh.read(-1 if size is None else size)

        def seek(self, offset: int, whence: int = 0) -> int:
            return self.fh.seek(offset, whence)

        def flush(self) -> None:
            self.fh.flush()

        def size(self) -> int:
            return self._end()

        def _end(self) -> int:
            here = self.fh.tell()
            end = self.fh.seek(0, 2)
            self.fh.seek(here)
            return end

        def close(self) -> None:
            size = self._end()  # py7zr may seek while writing, so tell() isn't the size
            self.fh.seek(0)
            try:
                writer.add_file(self.name, self.fh, size, self.mtime)
            finally:
                self.fh.close()
                self.path.unlink(missing_ok=True)

    try:
        with py7zr.SevenZipFile(path, "r") as archive:
            if archive.needs_password():
                raise ConversionError("Password-protected archives aren't supported.")
            entries = {}
            for info in archive.list():
                name = safe_name(info.filename)
                if name is None or info.is_symlink:
                    continue
                budget.entry()
                mtime = info.creationtime.timestamp() if info.creationtime else time.time()
                if info.is_directory:
                    writer.add_dir(name, mtime)
                else:
                    entries[info.filename] = (name, mtime)

            class Factory(WriterFactory):
                def create(self, filename: str) -> Py7zIO:
                    name, mtime = entries.get(filename, (None, 0.0))
                    if name is None:
                        from py7zr.io import NullIO

                        return NullIO()
                    return SpoolIO(name, mtime)

            archive.extractall(factory=Factory())
    finally:
        shutil.rmtree(spool, ignore_errors=True)


READERS = {"zip": _copy_zip, "tar": _copy_tar, "tar.gz": _copy_tar, "7z": _copy_7z}


class ArchiveEngine(Engine):
    name = "archive"

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs(ARCHIVES, ARCHIVES)

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        import py7zr

        src, dst = formats_of(input_path, output_path)
        budget = Budget()
        writer = open_writer(dst, output_path)
        try:
            READERS[src](input_path, writer, budget)
        except (zipfile.BadZipFile, tarfile.TarError, py7zr.Bad7zFile, EOFError) as exc:
            raise CorruptInputError("This archive appears to be corrupted.") from exc
        finally:
            writer.close()
        return [output_path]
