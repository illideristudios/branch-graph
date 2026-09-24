"""Entities and pure rules. No I/O, no git, no language."""

from __future__ import annotations

import fnmatch
import re
from operator import attrgetter
from dataclasses import dataclass, field

ModuleId = tuple[str, ...]


def name(module: ModuleId) -> str:
    return ".".join(module)


@dataclass(frozen=True)
class Edge:
    src: ModuleId
    dst: ModuleId
    file: str
    line: int

    @property
    def key(self) -> str:
        return f"{name(self.src)} -> {name(self.dst)}"


@dataclass
class Graph:
    files: dict[str, ModuleId] = field(default_factory=dict)
    edges: dict[tuple[ModuleId, ModuleId], Edge] = field(default_factory=dict)

    @property
    def nodes(self) -> set[ModuleId]:
        return set(self.files.values())

    def add(self, edge: Edge) -> None:
        """Keep the first file:line that creates an edge; drop self-edges."""
        if edge.src != edge.dst:
            self.edges.setdefault((edge.src, edge.dst), edge)


def collapse(graph: Graph, depth: int) -> Graph:
    out = Graph(files={path: module[:depth] for path, module in graph.files.items()})
    for e in sorted(graph.edges.values(), key=lambda e: (e.file, e.line)):
        out.add(Edge(e.src[:depth], e.dst[:depth], e.file, e.line))
    return out


@dataclass
class BranchDiff:
    base: Graph
    head: Graph
    added: set[ModuleId]
    removed: set[ModuleId]
    changed: dict[ModuleId, tuple[int, int]]
    edges_added: list[Edge]
    edges_removed: list[Edge]
    numstat: dict[str, tuple[int, int]]


def diff(base: Graph, head: Graph, numstat: dict[str, tuple[int, int]]) -> BranchDiff:
    """numstat: {path: (lines added, lines removed)} between the two revisions."""
    both = base.nodes & head.nodes
    changed: dict[ModuleId, tuple[int, int]] = {}
    for path, (plus, minus) in numstat.items():
        module = head.files.get(path) or base.files.get(path)
        if module in both and (plus or minus):
            p, m = changed.get(module, (0, 0))
            changed[module] = (p + plus, m + minus)
    order = attrgetter("file", "line")
    return BranchDiff(
        base=base,
        head=head,
        added=head.nodes - base.nodes,
        removed=base.nodes - head.nodes,
        changed=changed,
        edges_added=sorted((e for k, e in head.edges.items() if k not in base.edges), key=order),
        edges_removed=sorted((e for k, e in base.edges.items() if k not in head.edges), key=order),
        numstat=numstat,
    )


Rules = list[tuple[str, str]]
RULES_BLOCK = re.compile(r"^```import-rules[ \t]*\n(.*?)^```", re.M | re.S)


def parse_rules(text: str) -> Rules | None:
    """The first ```import-rules fence: one `A -> B` glob pair per line. None when there is no fence."""
    block = RULES_BLOCK.search(text)
    if not block:
        return None
    pairs = (line.split("->") for line in block.group(1).splitlines() if "->" in line and not line.lstrip().startswith("#"))
    return [(a.strip(), b.strip()) for a, b in pairs]


def verdict(edge: Edge, rules: Rules | None) -> str:
    if rules is None:
        return "no rules"
    src, dst = name(edge.src), name(edge.dst)
    return "allowed" if any(fnmatch.fnmatchcase(src, a) and fnmatch.fnmatchcase(dst, b) for a, b in rules) else "drift"
