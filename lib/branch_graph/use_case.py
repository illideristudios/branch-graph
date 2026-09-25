"""Build a revision's module graph and diff two of them. Depends on ports and domain only."""

from __future__ import annotations

from typing import Callable

from .domain import BranchDiff, Edge, Graph, collapse, diff
from .ports import LanguageModule, RevisionSource

Selector = Callable[[str], "LanguageModule | None"]


def build_graph(source: RevisionSource, select: Selector, rev: str, root: str) -> Graph:
    owners = {path: lang for path in source.files(rev, root) if (lang := select(path))}
    text = source.read_all(rev, list(owners))
    graph = Graph(files={path: m for path, lang in owners.items() if (m := lang.module_of(path, root, text[path]))})
    known = graph.nodes
    for path, module in graph.files.items():
        for dst, line in owners[path].imports(path, module, text[path], known):
            graph.add(Edge(module, dst, path, line))
    return graph


def branch_graph(source: RevisionSource, select: Selector, base: str, head: str, root: str, depth: int) -> BranchDiff:
    graphs = [collapse(build_graph(source, select, rev, root), depth) for rev in (base, head)]
    return diff(*graphs, source.numstat(base, head, root))
