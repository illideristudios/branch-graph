"""Code metrics as branch deltas: entities and pure rules. No I/O, no git, no tool.

Providers (`providers/`) turn source text into `Measures`; this module pairs the two revisions' functions, keeps the ones
the branch touched, attaches coverage, and rolls them up by class and by module.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from .domain import ModuleId

Lines = dict[str, tuple[set[int], set[int]]]  # path -> (base lines removed or changed, head lines added or changed)
Coverage = dict[str, dict[int, int]]  # path -> {line: hits}; a line absent from a report is not executable


@dataclass(frozen=True)
class Func:
    path: str
    name: str
    cls: str | None
    start: int
    end: int
    values: dict[str, float] = field(default_factory=dict, compare=False, hash=False)  # e.g. ccn, nloc, params


@dataclass(frozen=True)
class Clone:
    """One duplicated block: every (path, first line, last line) where it occurs."""

    snippets: tuple[tuple[str, int, int], ...]


@dataclass
class Measures:
    functions: list[Func] = field(default_factory=list)
    files: dict[str, dict[str, float]] = field(default_factory=dict)  # per-file values, e.g. mi
    clones: list[Clone] = field(default_factory=list)

    def merge(self, other: Measures) -> Measures:
        files = {p: dict(v) for p, v in self.files.items()}
        for path, values in other.files.items():
            files.setdefault(path, {}).update(values)
        return Measures(self.functions + other.functions, files, self.clones + other.clones)


@dataclass
class Row:
    """A function the branch touched: its base and head versions (one may be None) and its head coverage."""

    path: str
    cls: str | None
    name: str
    base: Func | None
    head: Func | None
    covered: int = 0
    executable: int = 0

    def value(self, side: str, key: str) -> float | None:
        f = self.base if side == "base" else self.head
        return f.values.get(key) if f else None

    def delta(self, key: str) -> float:
        return (self.value("head", key) or 0) - (self.value("base", key) or 0)

    @property
    def coverage(self) -> float | None:
        return self.covered / self.executable if self.executable else None


def overlaps(f: Func, lines: set[int]) -> bool:
    return any(f.start <= n <= f.end for n in lines)


def _keyed(funcs: list[Func]) -> dict[tuple[str, str | None, str, int], Func]:
    """(path, class, name, ordinal): the ordinal tells overloads and redefinitions of one name apart."""
    seen: dict[tuple[str, str | None, str], int] = defaultdict(int)
    out = {}
    for f in sorted(funcs, key=lambda f: (f.path, f.start)):
        k = (f.path, f.cls, f.name)
        out[(*k, seen[k])] = f
        seen[k] += 1
    return out


def rows(base: list[Func], head: list[Func], changed: Lines, coverage: Coverage | None = None) -> list[Row]:
    """Functions whose lines the branch changed on either side, paired across the revisions."""
    b, h = _keyed(base), _keyed(head)
    out = []
    for key in sorted(b.keys() | h.keys(), key=lambda k: (k[0], k[1] or "", k[2], k[3])):
        old, new = changed.get(key[0], (set(), set()))
        bf, hf = b.get(key), h.get(key)
        if (bf and overlaps(bf, old)) or (hf and overlaps(hf, new)):
            row = Row(key[0], key[1], key[2], bf, hf)
            if hf and coverage and (hits := coverage.get(hf.path)):
                lines = [n for n in range(hf.start, hf.end + 1) if n in hits]
                row.executable, row.covered = len(lines), sum(hits[n] > 0 for n in lines)
            out.append(row)
    return out


def touching(clones: list[Clone], changed: Lines) -> list[Clone]:
    """Clones with at least one occurrence on a head line the branch added or changed: duplication the branch wrote."""
    return [c for c in clones if any(any(s <= n <= e for n in changed.get(p, (set(), set()))[1]) for p, s, e in c.snippets)]


@dataclass
class Rollup:
    functions: int = 0
    ccn_delta: float = 0
    ccn_max: float = 0
    covered: int = 0
    executable: int = 0
    clones: int = 0

    @property
    def coverage(self) -> float | None:
        return self.covered / self.executable if self.executable else None


def rollup(rows_: list[Row], clones: list[Clone], module_of: Callable[[str], ModuleId | None], changed: Lines,
           coverage: Coverage | None = None) -> dict[ModuleId, Rollup]:
    """Per module: touched functions, the change in total complexity, the worst head complexity, clones, and diff
    coverage (the share of changed, executable head lines that ran)."""
    out: dict[ModuleId, Rollup] = defaultdict(Rollup)
    for r in rows_:
        if (m := module_of(r.path)) is not None:
            u = out[m]
            u.functions += 1
            u.ccn_delta += r.delta("ccn")
            u.ccn_max = max(u.ccn_max, r.value("head", "ccn") or 0)
    for c in clones:
        for m in {module_of(p) for p, _, _ in c.snippets} - {None}:
            out[m].clones += 1
    for path, (_, new) in changed.items():
        hits = (coverage or {}).get(path)
        if hits and (m := module_of(path)) is not None and (lines := [n for n in new if n in hits]):
            out[m].executable += len(lines)
            out[m].covered += sum(hits[n] > 0 for n in lines)
    return dict(out)


def innermost(classes: list[tuple[str, int, int]], line: int) -> str | None:
    """The name of the innermost (name, start, end) range holding `line`."""
    holding = [c for c in classes if c[1] <= line <= c[2]]
    return max(holding, key=lambda c: c[1])[0] if holding else None


@dataclass
class Report:
    """Everything the page shows about metrics. `tools` is (name, version, what it measures) for each installed provider."""

    rows: list[Row]
    clones: list[Clone]
    base_files: dict[str, dict[str, float]]
    head_files: dict[str, dict[str, float]]
    modules: dict[ModuleId, Rollup]
    tools: list[tuple[str, str, str]]
    reports: list[str]
