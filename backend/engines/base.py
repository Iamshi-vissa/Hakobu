"""Common engine interface, conversion options and a guarded subprocess runner."""

from __future__ import annotations

import logging
import os
import resource
import signal
import subprocess
import tempfile
import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from functools import cached_property
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.formats import extension_of

log = logging.getLogger(__name__)

ProgressFn = Callable[[float], None]
"""Receives a fraction in [0, 1] for the current step."""

Pair = tuple[str, str]


class ConversionOptions(BaseModel):
    """User-tunable options. Every engine ignores the options that don't apply to it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Images (also used for PDF → image rendering size)
    width: Annotated[int, Field(ge=1, le=16384)] | None = None
    height: Annotated[int, Field(ge=1, le=16384)] | None = None
    quality: Annotated[int, Field(ge=1, le=100)] | None = None
    strip_metadata: bool = False
    dpi: Annotated[int, Field(ge=36, le=600)] | None = None
    # Audio / video
    bitrate: Annotated[str, Field(pattern=r"^\d{2,5}k$")] | None = None
    sample_rate: Annotated[int, Field(ge=8000, le=192000)] | None = None
    trim_start: Annotated[float, Field(ge=0)] | None = None
    trim_end: Annotated[float, Field(gt=0)] | None = None
    # PDF → PDF operations
    pdf_compress: bool = False
    pdf_split: bool = False

    def cache_key(self) -> str:
        """Canonical, order-independent representation for result caching."""
        return self.model_dump_json(exclude_defaults=True)


class ConversionError(Exception):
    """A conversion failed; ``str(exc)`` is safe to show to users."""


class CorruptInputError(ConversionError):
    """The input could not be parsed."""


class Engine(ABC):
    """A converter engine declares the (src, dst) pairs it handles and performs them."""

    name: str = "engine"
    #: Pairs whose output may be several files; the registry never chains *from* them.
    terminal_pairs: frozenset[Pair] = frozenset()

    @abstractmethod
    def supported_pairs(self) -> frozenset[Pair]:
        """All (source_format, target_format) pairs this engine converts directly."""

    def can_convert(self, src: str, dst: str) -> bool:
        return (src, dst) in self._pairs

    @cached_property
    def _pairs(self) -> frozenset[Pair]:
        return self.supported_pairs()

    def available(self) -> bool:
        """Whether the engine's external dependencies are present."""
        return True

    @abstractmethod
    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        """Convert ``input_path`` to ``output_path`` and return the produced files.

        Formats are implied by the canonical extensions of both paths (see
        :func:`formats_of`). Most conversions return ``[output_path]``; multi-output conversions (e.g. a
        PDF rendered to one PNG per page) write siblings of ``output_path`` instead.
        """


def formats_of(input_path: Path, output_path: Path) -> Pair:
    """(src, dst) format ids from the canonical extensions the worker gives files."""
    src, dst = extension_of(input_path.name), extension_of(output_path.name)
    if src is None or dst is None:
        raise ConversionError("unrecognised file extension")
    return src, dst


def pairs(sources: Sequence[str], targets: Sequence[str]) -> frozenset[Pair]:
    """Every (src, dst) combination with ``src != dst``."""
    return frozenset((s, d) for s in sources for d in targets if s != d)


def _limit_memory(memory_mb: int) -> Callable[[], None]:
    def apply() -> None:
        limit = memory_mb * 1024 * 1024
        # RLIMIT_DATA (not AS) so tools that reserve large virtual ranges still start.
        resource.setrlimit(resource.RLIMIT_DATA, (limit, limit))

    return apply


def run_subprocess(
    args: Sequence[str | os.PathLike[str]],
    *,
    timeout: float | None = None,
    memory_mb: int | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    on_line: Callable[[str], None] | None = None,
) -> None:
    """Run a command with a timeout and memory cap; never through a shell.

    ``on_line`` receives stdout lines as they arrive (used for FFmpeg progress).
    Raises :class:`ConversionError` on non-zero exit or timeout.
    """
    settings = get_settings()
    timeout = timeout or settings.subprocess_timeout_seconds
    memory_mb = memory_mb or settings.subprocess_memory_mb
    tool = Path(str(args[0])).name
    with tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(  # noqa: S603 - argv list, no shell
            [str(a) for a in args],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if on_line else subprocess.DEVNULL,
            stderr=stderr,
            cwd=cwd,
            env=env,
            text=bool(on_line),
            start_new_session=True,  # own process group so a timeout kills children too
            preexec_fn=_limit_memory(memory_mb),  # noqa: PLW1509 - workers are single-threaded here
        )
        timed_out = threading.Event()

        def kill() -> None:
            timed_out.set()
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        timer = threading.Timer(timeout, kill)
        timer.start()
        try:
            if on_line and proc.stdout:
                for line in proc.stdout:
                    on_line(line.rstrip("\n"))
            proc.wait()
        finally:
            timer.cancel()
        if timed_out.is_set():
            raise ConversionError(f"{tool} timed out after {int(timeout)}s")
        if proc.returncode != 0:
            stderr.seek(0)
            tail = stderr.read()[-400:].decode(errors="replace").strip()
            # Tool diagnostics only (never file contents) at debug level.
            log.debug("%s exited %s: %s", tool, proc.returncode, tail)
            raise ConversionError(f"{tool} failed (exit code {proc.returncode})")
