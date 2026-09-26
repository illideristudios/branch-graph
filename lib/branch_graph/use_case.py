"""Build a revision's module graph and diff two of them. Depends on ports and domain only."""

from __future__ import annotations

from typing import Callable

from dataclasses import replace

from . import metrics
from .domain import BranchDiff, Edge, Graph, collapse, diff
from .metrics import Coverage, Func, Measures
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


def _attribute(funcs: list[Func], text: dict[str, str], select: Selector) -> list[Func]:
    """Give a function its class from the language's own class ranges when the provider did not name one."""
    cache: dict[str, list] = {}
    out = []
    for f in funcs:
        lang = select(f.path)
        if f.cls is None and hasattr(lang, "classes") and f.path in text:
            classes = cache.setdefault(f.path, lang.classes(text[f.path]))
            f = replace(f, cls=metrics.innermost(classes, f.start))
        out.append(f)
    return out


def measure(source: RevisionSource, select: Selector, providers: list, base: str, head: str, root: str, bd: BranchDiff,
            coverage: Coverage | None = None, reports: list[str] | None = None, dup_scope: str = "modules") -> metrics.Report:
    """Metrics of the functions the branch touched, both revisions, and the duplication it wrote.
    dup_scope: where a copy is looked for: "changed" files, the "modules" they belong to, or the whole "root"."""
    changed = {p: lines for p, lines in source.changed_lines(base, head, root).items() if select(p)}
    in_base = sorted(p for p in changed if p in bd.base.files)
    in_head = sorted(p for p in changed if p in bd.head.files)
    touched = {bd.head.files[p] for p in in_head}
    scope = {"changed": in_head, "root": sorted(bd.head.files),
             "modules": sorted(p for p, m in bd.head.files.items() if m in touched)}[dup_scope]
    old, new = (source.read_all(base, in_base), source.read_all(head, scope)) if providers else ({}, {})
    bm, hm = Measures(), Measures()
    for p in providers:
        bm = bm.merge(p.measure(old, set(in_base), clones=False))
        hm = hm.merge(p.measure(new, set(in_head), clones=True))
    rows = metrics.rows(_attribute(bm.functions, old, select), _attribute(hm.functions, new, select), changed, coverage)
    clones = metrics.touching(hm.clones, changed)
    module_of = lambda path: bd.head.files.get(path) or bd.base.files.get(path)  # noqa: E731
    return metrics.Report(rows, clones, bm.files, hm.files, metrics.rollup(rows, clones, module_of, changed, coverage),
                          [(p.name, p.version(), p.measures) for p in providers], reports or [])
