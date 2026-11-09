"""Central conversion registry.

Engines contribute directed edges (src → dst) to a format graph. The graph is built
once and, because it is small (≈50 nodes), the shortest conversion chain from every
source to every reachable target is precomputed with one BFS per source.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from app.formats import FORMATS, POPULARITY_RANK
from engines import ALL_ENGINES
from engines.base import ConversionOptions, Engine

MAX_CHAIN_LENGTH = 3


@dataclass(frozen=True, slots=True)
class Step:
    src: str
    dst: str
    engine: Engine


@dataclass(frozen=True, slots=True)
class Target:
    format: str
    steps: int


class UnsupportedConversion(Exception):
    def __init__(self, src: str | None, dst: str) -> None:
        source = FORMATS[src].label if src in FORMATS else "this file"
        target = FORMATS[dst].label if dst in FORMATS else dst
        super().__init__(f"Sorry, Hakobu can't convert {source} to {target} yet.")


class ConversionRegistry:
    def __init__(self, engines: list[Engine]) -> None:
        # The first engine registered for a pair wins, so list order is priority order.
        self._edges: dict[str, dict[str, Engine]] = {}
        self._transformers: dict[str, Engine] = {}
        for engine in engines:
            for src, dst in sorted(engine.supported_pairs()):
                self._edges.setdefault(src, {}).setdefault(dst, engine)
            for fmt in engine.transforms:
                self._transformers.setdefault(fmt, engine)
        self._paths: dict[str, dict[str, tuple[Step, ...]]] = {src: self._bfs(src) for src in FORMATS}

    def _bfs(self, source: str) -> dict[str, tuple[Step, ...]]:
        paths: dict[str, tuple[Step, ...]] = {source: ()}
        queue = deque([source])
        while queue:
            node = queue.popleft()
            path = paths[node]
            if len(path) >= MAX_CHAIN_LENGTH:
                continue
            if path and (path[-1].src, path[-1].dst) in path[-1].engine.terminal_pairs:
                continue  # multi-output steps can only end a chain
            # Visit popular formats first so ties resolve to sensible intermediates.
            for dst in sorted(self._edges.get(node, {}), key=_rank):
                engine = self._edges[node][dst]
                if dst in paths or (path and (node, dst) in engine.entry_only_pairs):
                    continue
                paths[dst] = (*path, Step(node, dst, engine))
                queue.append(dst)
        del paths[source]
        return paths

    def path(self, src: str, dst: str) -> tuple[Step, ...]:
        """Shortest chain of steps for src → dst; empty when src == dst."""
        if src == dst:
            return ()
        try:
            return self._paths[src][dst]
        except KeyError:
            raise UnsupportedConversion(src, dst) from None

    def plan(self, src: str, dst: str, options: ConversionOptions) -> tuple[Step, ...]:
        """Steps to run for a job. Same-format jobs are a no-op (the original file is
        returned) unless options ask for processing an engine can do in place."""
        if src == dst and options != ConversionOptions() and src in self._transformers:
            return (Step(src, dst, self._transformers[src]),)
        return self.path(src, dst)

    def targets(self, src: str) -> list[Target]:
        """Reachable targets, most likely choices first."""
        category = FORMATS[src].category
        reachable = self._paths.get(src, {})
        return sorted(
            (Target(dst, len(steps)) for dst, steps in reachable.items()),
            key=lambda t: (FORMATS[t.format].category != category, t.steps, _rank(t.format)),
        )

    def matrix(self) -> dict[str, list[Target]]:
        return {src: self.targets(src) for src in FORMATS if self._paths.get(src)}


def _rank(fmt: str) -> int:
    return POPULARITY_RANK.get(fmt, len(POPULARITY_RANK))


@lru_cache
def get_registry() -> ConversionRegistry:
    return ConversionRegistry([engine for engine in ALL_ENGINES if engine.available()])
