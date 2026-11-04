"""Conversion graph: direct pairs, BFS chains, ordering and chain rules."""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.formats import FORMATS
from engines import ALL_ENGINES
from engines.base import ConversionOptions
from registry import MAX_CHAIN_LENGTH, ConversionRegistry, UnsupportedConversion, get_registry


@pytest.fixture(scope="module")
def registry() -> ConversionRegistry:
    return get_registry()


def test_engines_follow_the_common_interface() -> None:
    for engine in ALL_ENGINES:
        pairs = engine.supported_pairs()
        assert pairs, engine.name
        for src, dst in pairs:
            assert src in FORMATS and dst in FORMATS, (engine.name, src, dst)
            assert src != dst
            assert engine.can_convert(src, dst)
        assert not engine.can_convert("png", "nonexistent")


def test_direct_and_chained_paths(registry: ConversionRegistry) -> None:
    assert [s.dst for s in registry.path("png", "jpg")] == ["jpg"]
    chain = registry.path("pptx", "png")
    assert [(s.src, s.dst) for s in chain] == [("pptx", "pdf"), ("pdf", "png")]


def test_every_path_is_shortest_and_well_formed(registry: ConversionRegistry) -> None:
    for src, targets in registry.matrix().items():
        for target in targets:
            steps = registry.path(src, target.format)
            assert 1 <= len(steps) <= MAX_CHAIN_LENGTH
            assert steps[0].src == src and steps[-1].dst == target.format
            for prev, nxt in pairwise(steps):
                assert prev.dst == nxt.src
                assert (prev.src, prev.dst) not in prev.engine.terminal_pairs, "multi-output step mid-chain"
            for step in steps[1:]:
                assert (step.src, step.dst) not in step.engine.entry_only_pairs, "entry-only step mid-chain"


def test_targets_put_same_category_and_direct_first(registry: ConversionRegistry) -> None:
    targets = registry.targets("png")
    assert targets[0].format == "jpg"
    categories = [FORMATS[t.format].category for t in targets]
    first_other = next(i for i, c in enumerate(categories) if c != "image")
    assert all(c == "image" for c in categories[:first_other])


def test_unsupported_pair_has_friendly_message(registry: ConversionRegistry) -> None:
    with pytest.raises(UnsupportedConversion, match="can't convert PNG to MP3"):
        registry.path("png", "mp3")


def test_same_format_is_noop_unless_options_need_work(registry: ConversionRegistry) -> None:
    assert registry.plan("png", "png", ConversionOptions()) == ()
    assert len(registry.plan("png", "png", ConversionOptions(width=10))) == 1
    assert len(registry.plan("pdf", "pdf", ConversionOptions(pdf_compress=True))) == 1
    assert registry.plan("zip", "zip", ConversionOptions(width=10)) == ()


def test_no_nonsense_chains(registry: ConversionRegistry) -> None:
    reachable = {t.format for t in registry.targets("gif")}
    assert "mp4" in reachable  # direct GIF → video is fine
    assert "mp3" not in reachable  # but GIFs have no audio to extract
    assert "docx" not in {t.format for t in registry.targets("heic")}
