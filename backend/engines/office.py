"""LibreOffice runner shared by the document, spreadsheet and presentation engines.

Conversions go to a pool of warm ``unoserver`` instances when configured
(``HAKOBU_UNOSERVER_INSTANCES``); otherwise each call runs a one-shot headless
``soffice``. Either way a slot is claimed with an exclusive file lock, so each
LibreOffice process / profile serves one conversion at a time. Every profile is
created with macro execution disabled.
"""

from __future__ import annotations

import fcntl
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings
from engines.base import (
    ConversionError,
    ConversionOptions,
    Engine,
    Pair,
    ProgressFn,
    formats_of,
    pairs,
    run_subprocess,
)

LOCK_DIR = Path(tempfile.gettempdir()) / "hakobu-office"
SLOT_WAIT_SECONDS = 120

# Macro security "very high" + macro execution disabled outright.
_REGISTRY_XCU = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry"
 xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
 <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
 <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop></item>
<item oor:path="/org.openoffice.Office.Common/Misc">
 <prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop></item>
</oor:items>
"""

# (target extension) -> (export filter, filter options) where autodetection is not enough.
EXPORT_FILTERS: dict[str, tuple[str, str]] = {
    "txt": ("Text (encoded)", "UTF8"),
    "csv": ("Text - txt - csv (StarCalc)", "44,34,76,1"),
}


def profile_dir(slot: int) -> Path:
    """Create (once) a macro-disabled LibreOffice profile for ``slot``; return its directory."""
    profile = LOCK_DIR / f"profile-{slot}"
    xcu = profile / "user" / "registrymodifications.xcu"
    if not xcu.exists():
        xcu.parent.mkdir(parents=True, exist_ok=True)
        xcu.write_text(_REGISTRY_XCU)
    return profile


def profile_uri(slot: int) -> str:
    return profile_dir(slot).as_uri()


def slot_count() -> int:
    settings = get_settings()
    return settings.unoserver_instances or settings.worker_concurrency


@contextmanager
def _claim_slot() -> Iterator[int]:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + SLOT_WAIT_SECONDS
    while True:
        for slot in range(slot_count()):
            with (LOCK_DIR / f"slot-{slot}.lock").open("w") as fh:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    continue
                try:
                    yield slot
                    return
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)
        if time.monotonic() > deadline:
            raise ConversionError("The document converter is busy; please retry shortly.")
        time.sleep(0.2)


def convert_with_office(input_path: Path, output_path: Path, target_ext: str) -> None:
    """Convert a file with LibreOffice into ``output_path`` (type given by ``target_ext``)."""
    settings = get_settings()
    export_filter = EXPORT_FILTERS.get(target_ext)
    with _claim_slot() as slot:
        if settings.unoserver_instances:
            args: list[str | Path] = [
                "unoconvert", "--host", settings.unoserver_host,
                "--port", str(settings.unoserver_base_port + slot),
                "--host-location", "local", "--convert-to", target_ext,
            ]
            if export_filter:
                args += ["--output-filter", export_filter[0], "--filter-option", export_filter[1]]
            run_subprocess([*args, input_path, output_path])
            return
        _convert_one_shot(input_path, output_path, target_ext, export_filter, slot)


def _convert_one_shot(
    input_path: Path, output_path: Path, target_ext: str,
    export_filter: tuple[str, str] | None, slot: int,
) -> None:
    convert_to = f"{target_ext}:{export_filter[0]}:{export_filter[1]}" if export_filter else target_ext
    with tempfile.TemporaryDirectory() as outdir:
        run_subprocess([
            "soffice", f"-env:UserInstallation={profile_uri(slot)}",
            "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo",
            "--convert-to", convert_to, "--outdir", outdir, input_path,
        ])
        produced = Path(outdir) / f"{input_path.stem}.{target_ext}"
        if not produced.exists():
            raise ConversionError("LibreOffice could not convert this file.")
        shutil.move(produced, output_path)


class OfficeEngine(Engine):
    """Base for LibreOffice-backed engines; subclasses only declare their formats."""

    INPUTS: tuple[str, ...] = ()
    OUTPUTS: tuple[str, ...] = ()

    def supported_pairs(self) -> frozenset[Pair]:
        return pairs(self.INPUTS, self.OUTPUTS)

    def available(self) -> bool:
        return shutil.which("soffice") is not None

    def convert(
        self,
        input_path: Path,
        output_path: Path,
        options: ConversionOptions,
        progress: ProgressFn | None = None,
    ) -> list[Path]:
        _, dst = formats_of(input_path, output_path)
        convert_with_office(input_path, output_path, dst)
        return [output_path]


class SpreadsheetEngine(OfficeEngine):
    """Workbook ↔ workbook (keeps formatting) and workbooks/CSV → PDF."""

    name = "libreoffice-calc"
    INPUTS = ("xlsx", "xls", "ods", "csv")
    OUTPUTS = ("xlsx", "xls", "ods", "pdf")


class PresentationEngine(OfficeEngine):
    name = "libreoffice-impress"
    INPUTS = ("pptx", "ppt", "odp")
    OUTPUTS = ("pptx", "ppt", "odp", "pdf")
