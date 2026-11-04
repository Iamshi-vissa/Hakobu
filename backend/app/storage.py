"""Storage abstraction.

All file bytes go through a :class:`Storage`. Only :class:`LocalStorage` ships today;
an S3 implementation needs to provide the same methods (``local_path`` would download
to a temp file, ``write_path`` would upload on exit, ``append`` maps to multipart upload).
"""

from __future__ import annotations

import os
import shutil
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path

import aiofiles
import aiofiles.os

from app.config import get_settings

CHUNK_SIZE = 1024 * 1024


class StorageLimitExceeded(Exception):
    """Raised when an append would grow an object beyond the allowed size."""


class Storage(ABC):
    @abstractmethod
    async def append(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        """Append streamed chunks to ``key``; return the new total size."""

    @abstractmethod
    async def iter_bytes(self, key: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        """Stream an object's bytes."""

    @abstractmethod
    def read_head(self, key: str, n: int) -> bytes:
        """Return the first ``n`` bytes of an object."""

    @abstractmethod
    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        """Yield a local filesystem path holding the object's bytes (read-only use)."""

    @abstractmethod
    @contextmanager
    def write_path(self, key: str) -> Iterator[Path]:
        """Yield a local path to write; the object is committed on clean exit."""

    @abstractmethod
    def move(self, src_key: str, dst_key: str) -> None: ...

    @abstractmethod
    def size(self, key: str) -> int: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...

    @abstractmethod
    def purge_older_than(self, seconds: int) -> int:
        """Delete objects older than ``seconds``; return how many top-level entries were removed."""


class LocalStorage(Storage):
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("storage key escapes root")
        return path

    async def append(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> int:
        path = self._path(key)
        await aiofiles.os.makedirs(path.parent, exist_ok=True)
        total = path.stat().st_size if path.exists() else 0
        async with aiofiles.open(path, "ab") as fh:
            async for chunk in chunks:
                total += len(chunk)
                if total > max_bytes:
                    raise StorageLimitExceeded
                await fh.write(chunk)
        return total

    async def iter_bytes(self, key: str, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        async with aiofiles.open(self._path(key), "rb") as fh:
            while chunk := await fh.read(chunk_size):
                yield chunk

    def read_head(self, key: str, n: int) -> bytes:
        with self._path(key).open("rb") as fh:
            return fh.read(n)

    @contextmanager
    def local_path(self, key: str) -> Iterator[Path]:
        yield self._path(key)

    @contextmanager
    def write_path(self, key: str) -> Iterator[Path]:
        final = self._path(key)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.with_name(f".{final.name}.part")
        try:
            yield tmp
            os.replace(tmp, final)
        finally:
            tmp.unlink(missing_ok=True)

    def move(self, src_key: str, dst_key: str) -> None:
        dst = self._path(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(self._path(src_key), dst)

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete_prefix(self, prefix: str) -> None:
        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)

    def purge_older_than(self, seconds: int) -> int:
        cutoff = time.time() - seconds
        removed = 0
        # Objects live two levels deep: <area>/<id>/...
        for area in self.root.iterdir():
            if not area.is_dir():
                continue
            for entry in area.iterdir():
                try:
                    if entry.stat().st_mtime < cutoff:
                        if entry.is_dir():
                            shutil.rmtree(entry, ignore_errors=True)
                        else:
                            entry.unlink(missing_ok=True)
                        removed += 1
                except FileNotFoundError:
                    continue
        return removed


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().data_dir)
    return _storage
