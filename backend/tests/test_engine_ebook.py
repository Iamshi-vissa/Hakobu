from __future__ import annotations

import pytest

from engines.ebook import EbookEngine
from tests.conftest import convert, detected, requires

pytestmark = requires("ebook-convert", "pandoc")
ENGINE = EbookEngine()


@pytest.mark.parametrize("dst", ["mobi", "azw3", "pdf", "docx", "txt"])
def test_epub_to(samples, tmp_path, dst: str) -> None:
    [out] = convert(ENGINE, samples.get("epub"), dst, tmp_path)
    assert detected(out) == dst


def test_mobi_to_epub(samples, tmp_path) -> None:
    [out] = convert(ENGINE, samples.get("mobi"), "epub", tmp_path)
    assert detected(out) == "epub"
