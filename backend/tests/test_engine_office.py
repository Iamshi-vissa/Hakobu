"""LibreOffice spreadsheet and presentation engines."""

from __future__ import annotations

import pytest

from engines.office import PresentationEngine, SpreadsheetEngine, profile_uri
from tests.conftest import convert, detected, requires

pytestmark = requires("soffice")


@pytest.mark.parametrize(("src", "dst"), [("xlsx", "ods"), ("xlsx", "pdf"), ("csv", "xls"), ("ods", "xlsx")])
def test_spreadsheets(samples, tmp_path, src: str, dst: str) -> None:
    [out] = convert(SpreadsheetEngine(), samples.get(src), dst, tmp_path)
    assert detected(out) == dst


@pytest.mark.parametrize(("src", "dst"), [("pptx", "pdf"), ("pptx", "odp"), ("odp", "pptx"), ("ppt", "pdf")])
def test_presentations(samples, tmp_path, src: str, dst: str) -> None:
    [out] = convert(PresentationEngine(), samples.get(src), dst, tmp_path)
    assert detected(out) == dst


def test_profiles_disable_macros() -> None:
    from pathlib import Path
    from urllib.parse import urlparse

    xcu = Path(urlparse(profile_uri(0)).path) / "user" / "registrymodifications.xcu"
    content = xcu.read_text()
    assert "DisableMacrosExecution" in content and "<value>true</value>" in content
