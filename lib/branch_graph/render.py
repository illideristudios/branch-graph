"""Presentation: a BranchDiff as Mermaid text and as one self-contained HTML page."""

from __future__ import annotations

import json
from pathlib import Path
import math
import re
from collections import Counter
from dataclasses import dataclass
from html import escape

from .domain import BranchDiff, Edge, ModuleId, name
from .metrics import Report, Rollup, Row

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
# ponytail: one fixed budget. Mermaid refuses more than 500 edges, and well before that a picture stops being readable:
# the OpenEMR fork at `--root .` wanted 561 (17 between touched modules, 544 out to context). Upgrade path: a flag.
EDGE_BUDGET = 150
# Every color on the page and in the diagram. `--colors` lays {"light": {token: value}, "dark": {...}} over these.
PALETTE = {
    "light": {"bg": "#f5f6f8", "surface": "#ffffff", "ink": "#1b2230", "muted": "#5e6878", "rule": "#d9dde4", "edge": "#6b7483",
              "accent": "#2f5bd3", "accent-bg": "#e6ebf7", "add": "#1f8a4c", "add-bg": "#e3f4ea", "del": "#c23b3b", "del-bg": "#fbe8e8",
              "drift": "#c2410c", "drift-bg": "#fdebdf", "hdr": "#6b56c4"},
    "dark": {"bg": "#12151b", "surface": "#1a1f28", "ink": "#e4e8ef", "muted": "#98a2b3", "rule": "#2a313d", "edge": "#7d8799",
             "accent": "#7aa2ff", "accent-bg": "#1c2742", "add": "#4cc27e", "add-bg": "#173323", "del": "#f07070", "del-bg": "#3a1a1c",
             "drift": "#fb923c", "drift-bg": "#3a2414", "hdr": "#b4a5f5"},
}
# A value lands inside <style>: no `;`, `:`, braces, quotes or angle brackets, so it cannot end the rule or the element.
COLOR_VALUE = re.compile(r"^[#\w(),.%/ -]+$")
HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def palette(overrides: dict | None = None) -> dict[str, dict[str, str]]:
    """PALETTE with `overrides` laid over it. Raises ValueError on an unknown mode or token, or a value that is not a plain CSS value."""
    out = {mode: dict(tokens) for mode, tokens in PALETTE.items()}
    for mode, tokens in (overrides or {}).items():
        if mode not in out or not isinstance(tokens, dict):
            raise ValueError(f"colors: {mode!r} is not a mode; use {{\"light\": {{...}}, \"dark\": {{...}}}}")
        for token, value in tokens.items():
            if token not in out[mode]:
                raise ValueError(f"colors: unknown token {token!r}; known: {', '.join(out[mode])}")
            if not isinstance(value, str) or not COLOR_VALUE.match(value):
                raise ValueError(f"colors: {mode}.{token} = {value!r} is not a plain CSS color")
            out[mode][token] = value
    return out


def _vars(tokens: dict[str, str]) -> str:
    return " ".join(f"--{k}: {v};" for k, v in tokens.items())


def summary(bd: BranchDiff, verdicts: dict[str, str], excluded: int | None = None, views: int | None = None) -> str:
    drift = sum(v == "drift" for v in verdicts.values())
    line = f"nodes +{len(bd.added)} −{len(bd.removed)} ~{len(bd.changed)} edges +{len(bd.edges_added)} −{len(bd.edges_removed)} drift={drift}"
    return line + (f" excluded={excluded}" if excluded is not None else "") + (f" views={views}" if views is not None else "")


def touched(bd: BranchDiff) -> set[ModuleId]:
    out = bd.added | bd.removed | set(bd.changed)
    for e in bd.edges_added + bd.edges_removed:
        out |= {e.src, e.dst}
    return out


def _grow(bd: BranchDiff, inside: list[ModuleId], cap: float = math.inf, budget: int = EDGE_BUDGET) -> list[ModuleId]:
    """`inside` (touched modules), then untouched modules one hop from them, most-connected first, while the drawn edges
    fit `budget` and the modules fit `cap`."""
    hot, have = touched(bd), set(inside)
    edges = set(bd.base.edges) | set(bd.head.edges)
    ties = Counter(b if a in have else a for a, b in edges if (a in have) != (b in have))
    used = sum(a in have and b in have for a, b in edges)
    out = list(inside)
    for module, n in sorted(ties.items(), key=lambda kv: (-kv[1], kv[0])):
        if module in hot:
            continue
        if used + n > budget or len(out) >= cap:
            break
        out.append(module)
        used += n
    return out


def drawn(bd: BranchDiff, budget: int = EDGE_BUDGET) -> tuple[list[ModuleId], int]:
    """The touched nodes, then modules one hop from them, most-connected first, while the drawn edges fit `budget`.
    Also the count of modules left out."""
    everything = bd.base.nodes | bd.head.nodes
    shown = _grow(bd, sorted(touched(bd) & everything), budget=budget)
    return sorted(shown), len(everything) - len(shown)


@dataclass
class View:
    title: str
    touched: list[ModuleId]
    shown: list[ModuleId]
    rest: int
    elsewhere: dict[ModuleId, int]


def views(bd: BranchDiff, max_nodes: int) -> list[View]:
    """The touched modules split into views of at most `max_nodes` drawn modules. A group grows through its own touched
    neighbours while the group plus every touched neighbour fits, and those neighbours are drawn as context, so an edge
    between two touched modules is drawn in the view of either end. Untouched context fills what is left."""
    if max_nodes < 3:
        raise ValueError(f"--max-nodes must be at least 3, got {max_nodes}")
    hot = touched(bd)
    everything = bd.base.nodes | bd.head.nodes
    near: dict[ModuleId, set[ModuleId]] = {m: set() for m in hot}
    for a, b in set(bd.base.edges) | set(bd.head.edges):
        if a in hot and b in hot:
            near[a].add(b)
            near[b].add(a)
    reach = lambda group: set(group).union(*(near[m] for m in group))  # noqa: E731
    # ponytail: greedy, recomputing reach per candidate (quadratic in a group's size); not a minimum number of views.
    free, groups = set(hot), []
    for seed in sorted(hot):
        if seed not in free:
            continue
        group, grew = [seed], True
        free.discard(seed)
        while grew:
            grew = False
            for m in sorted(reach(group) & free):
                if len(reach(group + [m])) <= max_nodes:
                    group.append(m)
                    free.discard(m)
                    grew = True
        groups.append(group)
    home = {m: k for k, group in enumerate(groups, 1) for m in group}
    out = []
    for group in groups:
        # Only a lone module can overflow; it keeps its best-connected touched neighbours, the likeliest to overflow too.
        # ponytail: two adjacent overflowing modules can still drop each other's edge (the test starts at N=5 for that).
        visitors = sorted(reach(group) - set(group), key=lambda m: (-len(near[m]), m))[: max_nodes - len(group)]
        shown = _grow(bd, group + visitors, cap=max_nodes)
        more = len(group) - 1
        title = name(group[0]) + (f" and {more} more" if more else "")
        out.append(View(title, group, shown, len(everything - hot - set(shown)), {m: home[m] for m in visitors}))
    return out


def edges(bd: BranchDiff) -> list[tuple[Edge, str]]:
    """Every edge of either revision, as (edge, "new" | "same" | "removed"): head's sorted, then the removed ones."""
    new = set(bd.head.edges) - set(bd.base.edges)
    return [(e, "new" if key in new else "same") for key, e in sorted(bd.head.edges.items())] + [(e, "removed") for e in bd.edges_removed]


def links(bd: BranchDiff, shown: list[ModuleId]) -> list[tuple[Edge, str]]:
    """The drawn edges, in Mermaid's link order: both ends drawn and one end touched."""
    hot, ids = touched(bd), set(shown)
    return [(e, k) for e, k in edges(bd) if e.src in ids and e.dst in ids and (e.src in hot or e.dst in hot)]


ARROW = {"new": "==>", "same": "-->", "removed": "-.->"}
PILL = {"new": ' <span class="pill added">new</span>', "removed": ' <span class="pill removed">removed</span>', "same": ""}
NO_CHANGES = '<p class="muted pad">No changes in this module.</p>'


def _ids(bd: BranchDiff) -> dict[ModuleId, int]:
    """One number per module of either revision, so every view and the page agree on `n<i>` and `#n-<i>`."""
    return {m: i for i, m in enumerate(sorted(bd.base.nodes | bd.head.nodes))}


def badge(u: Rollup) -> str:
    """The metrics line under a module's name: complexity change, diff coverage, duplication written."""
    parts = [f"cx {u.ccn_delta:+g}"] if u.functions else []
    parts += [f"cov {u.coverage:.0%}"] if u.coverage is not None else []
    parts += [f"dup {u.clones}"] if u.clones else []
    return " · ".join(parts)


def badges(report: Report | None) -> dict[ModuleId, str]:
    return {m: b for m, u in report.modules.items() if (b := badge(u))} if report else {}


def mermaid(bd: BranchDiff, verdicts: dict[str, str], shown: list[ModuleId], rest: int, elsewhere: dict[ModuleId, int] | None = None,
            badges: dict[ModuleId, str] | None = None) -> str:
    every = _ids(bd)
    ids = {m: f"n{every[m]}" for m in shown}
    elsewhere = elsewhere or {}
    lines = ["flowchart LR"]
    for m, nid in ids.items():
        label = name(m) + (f"<br/>+{bd.changed[m][0]} −{bd.changed[m][1]}" if m in bd.changed else "")
        label += f"<br/>in view {elsewhere[m]}" if m in elsewhere else ""
        label += f"<br/>{badges[m]}" if badges and m in badges else ""
        cls = ":::added" if m in bd.added else ":::removed" if m in bd.removed else ":::changed" if m in bd.changed else ""
        lines.append(f'  {nid}["{label}"]{cls}')
    if rest:
        lines.append(f'  more["… {rest} more modules untouched"]:::more')
    red = []
    for i, (e, kind) in enumerate(links(bd, shown)):
        lines.append(f"  {ids[e.src]} {ARROW[kind]} {ids[e.dst]}")
        if kind == "new" and verdicts.get(e.key) == "drift":
            red.append(i)
    for nid in ids.values():
        lines.append(f'  click {nid} href "#n-{nid[1:]}" _self')
    lines += [
        # Shape only: colors come from the page's palette, by class, so they follow --colors and dark mode.
        "  classDef added stroke-width:2px",
        "  classDef removed stroke-width:2px,stroke-dasharray:5 3",
        "  classDef changed stroke-width:2px",
        "  classDef more fill:none,stroke:none",
    ]
    if red:
        lines.append(f"  linkStyle {','.join(map(str, red))} stroke-width:3px")
    return "\n".join(lines) + "\n"


def view_mermaid(bd: BranchDiff, verdicts: dict[str, str], view: View, badges: dict[ModuleId, str] | None = None) -> str:
    return f"%% view: {view.title}\n" + mermaid(bd, verdicts, view.shown, view.rest, view.elsewhere, badges)


def _files(text: str) -> list[tuple[str, list[str]]]:
    """`git diff` text as (path, lines) per file. With --no-renames both header paths are the same, so it is the first half."""
    out: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("diff --git a/"):
            both = line[len("diff --git a/"):]
            out.append((both[: (len(both) - 3) // 2], []))
        elif out:
            out[-1][1].append(line)
    return out


class Anchors:
    """Every diff line and file on the page gets an id; `where` finds the one for a (path, side, line) of an edge."""

    def __init__(self):
        self.files = 0
        self.lines: dict[tuple[str, str, int], str] = {}
        self.paths: dict[str, str] = {}

    def diff_html(self, text: str, numstat: dict[str, tuple[int, int]]) -> str:
        return "\n".join(self._file_html(path, lines, numstat.get(path)) for path, lines in _files(text))

    def _file_html(self, path: str, lines: list[str], stat: tuple[int, int] | None) -> str:
        fid = f"f{self.files}"
        self.files += 1
        self.paths.setdefault(path, fid)
        rows, old, new = [], None, None
        for j, line in enumerate(lines):
            if hunk := HUNK.match(line):
                old, new = int(hunk.group(1)), int(hunk.group(2))
                rows.append(f'<span class="l hdr">{escape(line)}</span>')
            elif old is None or line.startswith("\\"):
                if not line.startswith(("index ", "--- ", "+++ ")):
                    rows.append(f'<span class="l meta">{escape(line)}</span>')
            else:
                kind = "add" if line.startswith("+") else "del" if line.startswith("-") else "ctx"
                o, n = (old if kind != "add" else None), (new if kind != "del" else None)
                lid = f"{fid}-{j}"
                if o is not None:
                    self.lines.setdefault((path, "o", o), lid)
                    old += 1
                if n is not None:
                    self.lines.setdefault((path, "n", n), lid)
                    new += 1
                rows.append(f'<span class="l {kind}" id="{lid}"><i>{o or ""}</i><i>{n or ""}</i>{escape(line)}</span>')
        counts = f' <span class="muted">+{stat[0]} −{stat[1]}</span>' if stat else ""
        return f'<div class="file" id="{fid}"><div class="fname mono">{escape(path)}{counts}</div><pre class="diff">{"".join(rows)}</pre></div>'

    def where(self, e: Edge, kind: str, panel: str | None) -> str | None:
        """The edge's own diff line, else its file's diff, else its source module's panel."""
        side = "o" if kind == "removed" else "n"
        return self.lines.get((e.file, side, e.line)) or self.paths.get(e.file) or panel


INSTALL_HINT = ('<p class="muted">No metrics library found. For complexity and duplication, <code>pip install lizard</code>; '
                'for Python maintainability, <code>pip install radon</code>, into the Python that runs branch-graph. '
                'Coverage comes from a report passed with <code>--coverage</code>.</p>')


def _num(v: float | None) -> str:
    return "—" if v is None else f"{v:g}"


def _change(b: float | None, h: float | None, higher_is_better: bool = False) -> str:
    """A table cell for a value before → after; worse or better only when both sides exist."""
    if b is not None and b == h:
        return f'<td class="num">{_num(h)}</td>'
    cls = ""
    if b is not None and h is not None:
        cls = " better" if (h > b) == higher_is_better else " worse"
    return f'<td class="num{cls}">{_num(b)} → {_num(h)}</td>'


def _pct(covered: int, executable: int) -> str:
    return f"{covered / executable:.0%}" if executable else "—"


def _metrics_section(report: Report, module_link) -> str:
    tools = "; ".join(f"{escape(n)} {escape(v)}: {escape(what)}" for n, v, what in report.tools)
    reports = ", ".join(escape(Path(r).name) for r in report.reports)
    head = f'<p class="muted">{tools or "no metrics library"}{"; coverage from " + reports if reports else ""}.</p>'
    if not report.tools and not report.reports:
        return f'<section id="metrics"><h2>Metrics</h2>{INSTALL_HINT}</section>'
    body = "".join(
        f"<tr><td>{module_link(m)}</td><td class=\"num\">{u.functions}</td>"
        f'<td class="num{" worse" if u.ccn_delta > 0 else " better" if u.ccn_delta < 0 else ""}">{u.ccn_delta:+g}</td>'
        f'<td class="num">{_num(u.ccn_max) if u.functions else "—"}</td><td class="num">{u.clones}</td>'
        f'<td class="num">{_pct(u.covered, u.executable)}</td></tr>'
        for m, u in sorted(report.modules.items())
    ) or '<tr><td colspan="6" class="muted">No function, clone or covered line the branch touched.</td></tr>'
    hint = "" if report.tools else INSTALL_HINT
    return (f'<section id="metrics"><h2>Metrics</h2>{head}{hint}<div class="scroll"><table><thead><tr><th>Module</th><th>Functions touched</th>'
            f'<th>Complexity Δ</th><th>Worst complexity</th><th>Duplication written</th><th>Diff coverage</th></tr></thead><tbody>{body}'
            '</tbody></table></div></section>')


def _metrics_panel(report: Report, paths: set[str], anchors: Anchors) -> str:
    """One module's touched functions by class, the duplication it wrote, and per-file values (radon's MI)."""
    out = []
    rows = [r for r in report.rows if r.path in paths]
    if rows:
        body, last = [], object()
        for r in sorted(rows, key=lambda r: (r.path, r.cls or "", (r.head or r.base).start)):
            if (r.path, r.cls) != last:
                cls = f"{escape(r.cls)} " if r.cls else ""
                body.append(f'<tr class="cls"><td colspan="5" class="mono">{cls}<span class="muted">{escape(r.path)}</span></td></tr>')
            last = (r.path, r.cls)
            f, side = (r.head, "n") if r.head else (r.base, "o")
            target = anchors.lines.get((r.path, side, f.start)) or anchors.paths.get(r.path)
            label = f"{escape(r.name)}{PILL['new'] if not r.base else PILL['removed'] if not r.head else ''}"
            where = f"{escape(r.path)}:{f.start}"
            cell = f'<a class="mono" href="#{target}" title="{where}">{label}</a>' if target else f'<span class="mono" title="{where}">{label}</span>'
            body.append(f"<tr><td>{cell}</td>{_change(r.value('base', 'ccn'), r.value('head', 'ccn'))}"
                        f"{_change(r.value('base', 'nloc'), r.value('head', 'nloc'))}{_change(r.value('base', 'params'), r.value('head', 'params'))}"
                        f'<td class="num">{_pct(r.covered, r.executable)}</td></tr>')
        out.append('<div class="metrics"><h3>Functions touched</h3><div class="scroll"><table><thead><tr><th>Function</th><th>Complexity</th>'
                   f'<th>Lines</th><th>Params</th><th>Coverage</th></tr></thead><tbody>{"".join(body)}</tbody></table></div></div>')
    clones = [c for c in report.clones if any(p in paths for p, _, _ in c.snippets)]
    if clones:
        def spot(p: str, a: int, b: int) -> str:
            target = anchors.lines.get((p, "n", a)) or anchors.paths.get(p)
            text = f"{escape(p)}:{a}–{b}"
            return f'<a class="mono" href="#{target}">{text}</a>' if target else f'<span class="mono">{text}</span>'
        li = "".join(f"<li>{' ≈ '.join(spot(*s) for s in c.snippets)}</li>" for c in clones)
        out.append(f'<div class="metrics"><h3>Duplication written <span class="muted">{len(clones)}</span></h3><ul>{li}</ul></div>')
    files = sorted(p for p in paths if p in report.base_files or p in report.head_files)
    if files:
        li = "".join(
            f'<li><span class="mono">{escape(p)}</span> maintainability '
            f'{_num(report.base_files.get(p, {}).get("mi"))} → {_num(report.head_files.get(p, {}).get("mi"))}</li>' for p in files)
        out.append(f'<div class="metrics"><h3>Files</h3><ul>{li}</ul></div>')
    return "".join(out)


def page(bd: BranchDiff, title: str, subtitle: str, diagrams: list[tuple[str, str, list[ModuleId]]], verdicts: dict[str, str],
         notes: dict[str, str], hunks: dict[ModuleId, str], shown: list[ModuleId], rest: int,
         colors: dict[str, dict[str, str]] | None = None, excluded: int | None = None, metrics: Report | None = None) -> str:
    """diagrams: (view title, Mermaid text, modules it draws); one untitled diagram when there are no views.
    shown: every drawn module, one panel each."""
    every_id = _ids(bd)
    ids = {m: f"n-{every_id[m]}" for m in shown}
    anchors = Anchors()
    diffs = {m: anchors.diff_html(hunks.get(m, ""), bd.numstat) for m in shown}
    every = edges(bd)
    href = lambda e, kind: anchors.where(e, kind, ids.get(e.src))  # noqa: E731

    def code(e: Edge, kind: str) -> str:
        target = href(e, kind)
        text = f"{escape(e.file)}:{e.line}"
        return f'<a class="mono" href="#{target}">{text}</a>' if target else f'<span class="mono">{text}</span>'

    rows = [(e, "new", verdicts.get(e.key, "")) for e in bd.edges_added] + [(e, "removed", "removed") for e in bd.edges_removed]
    table = "\n".join(
        f'<tr><td class="mono">{escape(e.key)}</td><td>{code(e, kind)}</td>'
        f'<td><span class="pill {escape(v.replace(" ", "-"))}">{escape(v)}</span></td><td>{escape(notes.get(e.key, ""))}</td></tr>'
        for e, kind, v in rows
    ) or '<tr><td colspan="4" class="muted">No import edges added or removed.</td></tr>'

    def module_link(m: ModuleId) -> str:
        return f'<a class="mono" href="#{ids[m]}">{escape(name(m))}</a>' if m in ids else f'<span class="mono">{escape(name(m))}</span>'

    def connections(m: ModuleId) -> str:
        order = {"new": 0, "removed": 1, "same": 2}
        out = []
        for title, mine, other in (("Imports", "src", "dst"), ("Imported by", "dst", "src")):
            items = sorted(((e, k) for e, k in every if getattr(e, mine) == m), key=lambda ek: (order[ek[1]], getattr(ek[0], other)))
            li = "".join(f"<li>{module_link(getattr(e, other))}{PILL[k]} {code(e, k)}</li>" for e, k in items)
            out.append(f'<div><h3>{title} <span class="muted">{len(items)}</span></h3><ul>{li or "<li class=muted>none</li>"}</ul></div>')
        return f'<div class="conn">{"".join(out)}</div>'

    paths_of: dict[ModuleId, set[str]] = {m: set() for m in shown}
    for path, m in {**bd.base.files, **bd.head.files}.items():
        if m in paths_of:
            paths_of[m].add(path)
    state = lambda m: "added" if m in bd.added else "removed" if m in bd.removed else "changed" if m in bd.changed else "context"  # noqa: E731
    details = "\n".join(
        f'<details id="{ids[m]}"><summary><span class="mono">{escape(name(m))}</span> <span class="pill {state(m)}">{state(m)}</span>'
        + (f' <span class="mono muted">+{bd.changed[m][0]} −{bd.changed[m][1]}</span>' if m in bd.changed else "")
        + f'</summary>{connections(m)}{_metrics_panel(metrics, paths_of[m], anchors) if metrics else ""}{diffs[m] or NO_CHANGES}</details>'
        for m in shown
    )
    data: dict[str, list] = {"links": []}
    graphs, drift = [], []
    for k, (view, mmd, drawn_here) in enumerate(diagrams, 1):
        gid = f"graph-{k}" if view else "graph"
        heading = f'<h3>View {k} · <span class="mono">{escape(view)}</span></h3>' if view else ""
        graphs.append(VIEW.format(heading=heading, gid=gid, first=len(data["links"]), mmd=escape(mmd)))
        drawn_links = links(bd, drawn_here)
        data["links"] += [{"href": href(e, kind), "title": f"{e.key}  {e.file}:{e.line}"} for e, kind in drawn_links]
        drift += [f"#{gid} svg #L_n{every_id[e.src]}_n{every_id[e.dst]}_{i}" for i, (e, kind) in enumerate(drawn_links)
                  if kind == "new" and verdicts.get(e.key) == "drift"]
    drift = ", ".join(drift)
    chips = [("added", f"+{len(bd.added)} modules"), ("removed", f"−{len(bd.removed)} modules"), ("changed", f"~{len(bd.changed)} changed"),
             ("context", f"+{len(bd.edges_added)} / −{len(bd.edges_removed)} edges"), ("drift", f"{sum(v == 'drift' for v in verdicts.values())} drift")]
    chips += [("context", f"{excluded} excluded")] if excluded is not None else []
    return TEMPLATE.format(
        title=escape(title), subtitle=escape(subtitle), cdn=MERMAID_CDN, graphs="\n".join(graphs), table=table, details=details,
        metrics=_metrics_section(metrics, module_link) if metrics else "",
        chips="".join(f'<span class="pill {c}">{escape(t)}</span>' for c, t in chips),
        rest=f"{rest} untouched modules not drawn." if rest else "",
        data=json.dumps(data).replace("</", "<\\/"),
        drift=f"{drift} {{ stroke: var(--drift) !important; }}" if drift else "",
        light=_vars((colors or PALETTE)["light"]), dark=_vars((colors or PALETTE)["dark"]),
    )


VIEW = """<div class="view">{heading}<div class="scroll"><div class="graph" id="{gid}" data-first="{first}"></div></div><p class="focus" hidden></p>
<pre class="mmd" hidden>{mmd}</pre></div>"""

TEMPLATE = """<meta charset="utf-8">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {{
  {light}
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; {dark} }} }}
:root[data-theme="dark"] {{ color-scheme: dark; {dark} }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.55 var(--sans); }}
main {{ max-width: 1100px; margin: 0 auto; padding: 28px 16px 64px; display: grid; gap: 28px; }}
h1 {{ font-size: 1.5rem; font-weight: 600; margin: 0; text-wrap: balance; }}
h2 {{ font-size: .78rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); margin: 0 0 10px; }}
header {{ display: grid; gap: 10px; }}
.mono {{ font-family: var(--mono); font-size: .86em; }}
.muted {{ color: var(--muted); }}
.chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.pill {{ display: inline-block; padding: 1px 9px; border-radius: 999px; font-size: .8rem; font-weight: 500; font-variant-numeric: tabular-nums; border: 1px solid var(--rule); color: var(--muted); }}
.pill.added, .pill.allowed {{ color: var(--add); background: var(--add-bg); border-color: transparent; }}
.pill.removed {{ color: var(--del); background: var(--del-bg); border-color: transparent; }}
.pill.drift {{ color: var(--drift); background: var(--drift-bg); border-color: transparent; }}
.pill.changed {{ color: var(--accent); border-color: var(--accent); }}
.scroll {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; }}
.graph {{ padding: 16px; min-height: 120px; }}
.graph svg {{ max-width: none; }}
.graph svg .flowchart-link {{ stroke: var(--edge); }}
.graph svg .marker {{ fill: var(--edge); stroke: var(--edge); }}
.graph svg .node rect, .graph svg .node polygon {{ fill: var(--surface); stroke: var(--rule); }}
.graph svg .node.added rect {{ fill: var(--add-bg); stroke: var(--add); }}
.graph svg .node.removed rect {{ fill: var(--del-bg); stroke: var(--del); }}
.graph svg .node.changed rect {{ fill: var(--accent-bg); stroke: var(--accent); }}
.graph svg .node.more rect {{ fill: none; stroke: none; }}
.graph svg .nodeLabel {{ color: var(--ink); }}
.graph svg .node.more .nodeLabel {{ color: var(--muted); }}
{drift}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
tr:last-child td {{ border-bottom: 0; }}
.modules {{ display: grid; gap: 8px; }}
details {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; scroll-margin-top: 16px; }}
details[open] {{ border-color: var(--accent); }}
summary {{ cursor: pointer; padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
.pad {{ margin: 0; padding: 10px 14px; border-top: 1px solid var(--rule); }}
.conn {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 4px 24px; padding: 10px 14px; border-top: 1px solid var(--rule); }}
.conn h3 {{ font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 0 0 4px; }}
.conn ul {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; max-height: 16rem; overflow-y: auto; }}
.conn li {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }}
a {{ color: var(--accent); text-underline-offset: 2px; }}
.file {{ border-top: 1px solid var(--rule); }}
.fname {{ padding: 8px 14px; background: var(--bg); position: sticky; left: 0; }}
pre.diff {{ margin: 0; padding: 4px 0 10px; overflow-x: auto; font: 12.5px/1.5 var(--mono); }}
pre.diff .l {{ display: block; min-width: max-content; padding-right: 14px; white-space: pre; }}
pre.diff .l i {{ display: inline-block; width: 4.5ch; padding-right: 1ch; text-align: right; font-style: normal; color: var(--muted); user-select: none; }}
pre.diff .add {{ color: var(--add); background: var(--add-bg); }}
pre.diff .del {{ color: var(--del); background: var(--del-bg); }}
pre.diff .hdr {{ color: var(--hdr); padding-left: 11ch; margin-top: 6px; }}
pre.diff .meta {{ color: var(--muted); padding-left: 11ch; }}
.flash {{ outline: 2px solid var(--accent); outline-offset: -2px; }}
.view + .view {{ margin-top: 20px; }}
.view h3 {{ font-size: .9rem; font-weight: 600; margin: 0 0 6px; }}
.legend {{ font-size: .85rem; color: var(--muted); margin: 8px 0 0; }}
.focus {{ margin: 8px 0 0; display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline; }}
.focus[hidden] {{ display: none; }}
.focus button {{ font: inherit; font-size: .85rem; color: var(--muted); background: none; border: 1px solid var(--rule); border-radius: 999px; padding: 0 10px; cursor: pointer; }}
.graph .focusing .flowchart-link:not(.hl) {{ opacity: .1; }}
.graph .focusing .node:not(.hl) {{ opacity: .3; }}
.graph .flowchart-link.hl {{ stroke-width: 3px !important; }}
.graph .hit {{ stroke: transparent !important; stroke-width: 14px !important; fill: none; pointer-events: stroke; cursor: pointer; }}
.graph .node {{ cursor: pointer; }}
td.num, th {{ font-variant-numeric: tabular-nums; }}
td.num {{ white-space: nowrap; }}
td.worse {{ color: var(--del); }}
td.better {{ color: var(--add); }}
tr.cls td {{ background: var(--bg); }}
.metrics {{ padding: 10px 14px; border-top: 1px solid var(--rule); }}
.metrics h3 {{ font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 600; margin: 0 0 6px; }}
.metrics ul {{ margin: 0; padding-left: 18px; display: grid; gap: 2px; }}
code {{ font-family: var(--mono); font-size: .86em; }}
</style>
<main>
  <header>
    <h1>{title}</h1>
    <div class="muted mono">{subtitle}</div>
    <div class="chips">{chips}</div>
  </header>
  <section>
    <h2>Module graph</h2>
{graphs}
    <p class="legend">Green: new module. Red dashed: removed. Blue: changed, with lines +added −removed. Thick arrow: new import. Orange arrow: drift from the import rules. Dashed arrow: import removed. {rest} Click a module to highlight its imports; click an arrow to go to the line that created it.</p>
  </section>
  <section>
    <h2>Import edges</h2>
    <div class="scroll"><table><thead><tr><th>Edge</th><th>Created at</th><th>Verdict</th><th>Why</th></tr></thead><tbody>
{table}
    </tbody></table></div>
  </section>
  {metrics}
  <section>
    <h2>Modules</h2>
    <div class="modules">
{details}
    </div>
  </section>
</main>
<script type="application/json" id="bg-data">{data}</script>
<script src="{cdn}"></script>
<script>
(function () {{
  var root = document.documentElement;
  var dark = root.dataset.theme === "dark" || (root.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  var data = JSON.parse(document.getElementById("bg-data").textContent);

  function go(id) {{
    var el = document.getElementById(id);
    if (!el) return;
    for (var d = el; d; d = d.parentElement) if (d.tagName === "DETAILS") d.open = true;
    el.scrollIntoView({{ block: el.tagName === "DETAILS" ? "start" : "center" }});
    el.classList.add("flash");
    setTimeout(function () {{ el.classList.remove("flash"); }}, 1600);
  }}
  document.addEventListener("click", function (ev) {{
    var a = ev.target.closest("a");
    var href = a && (a.getAttribute("href") || a.getAttribute("xlink:href"));
    if (!href || href.charAt(0) !== "#") return;
    ev.preventDefault();
    var graph = a.closest(".graph");
    if (graph) focus(graph, href.slice(1)); else go(href.slice(1));
  }});
  var graphs = document.querySelectorAll(".graph");
  document.addEventListener("keydown", function (ev) {{ if (ev.key === "Escape") graphs.forEach(function (g) {{ focus(g, null); }}); }});

  function focus(graph, panel) {{
    var svg = graph.querySelector("svg"), bar = graph.closest(".view").querySelector(".focus");
    if (!svg) return;
    var nid = panel && "n" + panel.slice(2);
    if (!panel || svg.dataset.focus === nid) {{ svg.classList.remove("focusing"); delete svg.dataset.focus; bar.hidden = true; return; }}
    svg.dataset.focus = nid;
    svg.classList.add("focusing");
    var near = {{}}, out = 0, into = 0;
    near[nid] = true;
    svg.querySelectorAll("path.flowchart-link").forEach(function (p) {{
      var m = /^L_(n\\d+)_(n\\d+)_\\d+$/.exec(p.id), on = !!m && (m[1] === nid || m[2] === nid);
      p.classList.toggle("hl", on);
      if (on) {{ near[m[1]] = near[m[2]] = true; if (m[1] === nid) out++; else into++; }}
    }});
    svg.querySelectorAll(".node").forEach(function (n) {{
      var m = /^flowchart-(n\\d+)-/.exec(n.id);
      n.classList.toggle("hl", !!m && !!near[m[1]]);
    }});
    var summary = document.querySelector("#" + panel + " summary .mono");
    bar.innerHTML = "";
    var b = document.createElement("strong"); b.className = "mono"; b.textContent = summary ? summary.textContent : panel;
    var c = document.createElement("span"); c.className = "muted"; c.textContent = "imports " + out + " · imported by " + into + " drawn";
    var l = document.createElement("a"); l.href = "#" + panel; l.textContent = "connections and diff ↓";
    var x = document.createElement("button"); x.type = "button"; x.textContent = "clear";
    x.addEventListener("click", function () {{ focus(graph, null); }});
    bar.append(b, c, l, x);
    bar.hidden = false;
  }}

  function arm(svg, first) {{
    svg.querySelectorAll("path.flowchart-link").forEach(function (p) {{
      var m = /_(\\d+)$/.exec(p.id), i = m && first + +m[1], link = m && data.links[i];
      if (!link) return;
      var hit = p.cloneNode(false);
      hit.removeAttribute("id"); hit.removeAttribute("marker-end"); hit.removeAttribute("style");
      hit.setAttribute("class", "hit"); hit.dataset.link = i;
      var t = document.createElementNS("http://www.w3.org/2000/svg", "title"); t.textContent = link.title;
      hit.appendChild(t);
      p.parentNode.insertBefore(hit, p.nextSibling);
    }});
  }}

  if (window.mermaid) mermaid.initialize({{ startOnLoad: false, securityLevel: "loose", theme: dark ? "dark" : "default", flowchart: {{ htmlLabels: true }} }});
  graphs.forEach(function (graph, k) {{
    if (!window.mermaid) {{ graph.textContent = "Mermaid did not load; the diagram source is in the page."; return; }}
    graph.addEventListener("click", function (ev) {{
      var hit = ev.target.closest(".hit");
      if (hit) go(data.links[+hit.dataset.link].href);
      else if (!ev.target.closest("a")) focus(graph, null);
    }});
    var text = graph.closest(".view").querySelector(".mmd").textContent;
    mermaid.render("g" + k, text).then(function (r) {{ graph.innerHTML = r.svg; arm(graph.querySelector("svg"), +graph.dataset.first); }});
  }});
}})();
</script>
"""
