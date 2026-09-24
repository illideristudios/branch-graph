"""Presentation: a BranchDiff as Mermaid text and as one self-contained HTML page."""

from __future__ import annotations

from html import escape

from .domain import BranchDiff, ModuleId, name

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"


def summary(bd: BranchDiff, verdicts: dict[str, str]) -> str:
    drift = sum(v == "drift" for v in verdicts.values())
    return f"nodes +{len(bd.added)} −{len(bd.removed)} ~{len(bd.changed)} edges +{len(bd.edges_added)} −{len(bd.edges_removed)} drift={drift}"


def touched(bd: BranchDiff) -> set[ModuleId]:
    out = bd.added | bd.removed | set(bd.changed)
    for e in bd.edges_added + bd.edges_removed:
        out |= {e.src, e.dst}
    return out


def drawn(bd: BranchDiff) -> tuple[list[ModuleId], int]:
    """The touched nodes plus everything one hop from them; the count of the rest."""
    touched_ = touched(bd)
    edges = list(bd.base.edges) + list(bd.head.edges)
    near = {b for a, b in edges if a in touched_} | {a for a, b in edges if b in touched_}
    everything = bd.base.nodes | bd.head.nodes
    shown = sorted((touched_ | near) & everything)
    return shown, len(everything) - len(shown)


def mermaid(bd: BranchDiff, verdicts: dict[str, str], shown: list[ModuleId], rest: int) -> str:
    hot = touched(bd)
    ids = {m: f"n{i}" for i, m in enumerate(shown)}
    lines = ["flowchart LR"]
    for m, nid in ids.items():
        label = name(m) + (f"<br/>+{bd.changed[m][0]} −{bd.changed[m][1]}" if m in bd.changed else "")
        cls = ":::added" if m in bd.added else ":::removed" if m in bd.removed else ":::changed" if m in bd.changed else ""
        lines.append(f'  {nid}["{label}"]{cls}')
    if rest:
        lines.append(f'  more["… {rest} more modules untouched"]:::more')
    links, red = 0, []
    new = {(e.src, e.dst): e for e in bd.edges_added}
    for (src, dst), e in sorted(bd.head.edges.items()):
        if src in ids and dst in ids and (src in hot or dst in hot):
            lines.append(f"  {ids[src]} {'==>' if (src, dst) in new else '-->'} {ids[dst]}")
            if verdicts.get(e.key) == "drift":
                red.append(links)
            links += 1
    for e in bd.edges_removed:
        if e.src in ids and e.dst in ids:
            lines.append(f"  {ids[e.src]} -.-> {ids[e.dst]}")
            links += 1
    for i, nid in enumerate(ids.values()):
        lines.append(f'  click {nid} href "#n-{i}" _self')
    lines += [
        "  classDef added fill:#d9f2e3,stroke:#1f8a4c,stroke-width:2px,color:#0d3a20",
        "  classDef removed fill:#fbe4e4,stroke:#c23b3b,stroke-width:2px,stroke-dasharray:5 3,color:#4a1111",
        "  classDef changed fill:#e6ebf7,stroke:#2f5bd3,stroke-width:2px,color:#14223f",
        "  classDef more fill:none,stroke:none,color:#7a8494",
    ]
    if red:
        lines.append(f"  linkStyle {','.join(map(str, red))} stroke:#d4481f,stroke-width:3px")
    return "\n".join(lines) + "\n"


def _hunk_html(text: str) -> str:
    out = []
    for line in text.splitlines():
        cls = "add" if line.startswith("+") and not line.startswith("+++") else "del" if line.startswith("-") and not line.startswith("---") else "hdr" if line.startswith(("@@", "diff ")) else ""
        out.append(f'<span class="{cls}">{escape(line)}</span>' if cls else escape(line))
    return "\n".join(out)


def page(bd: BranchDiff, title: str, subtitle: str, mmd: str, verdicts: dict[str, str], notes: dict[str, str], hunks: dict[ModuleId, str],
         shown: list[ModuleId], rest: int) -> str:
    ids = {m: f"n-{i}" for i, m in enumerate(shown)}
    rows = [(e, verdicts.get(e.key, "")) for e in bd.edges_added] + [(e, "removed") for e in bd.edges_removed]
    table = "\n".join(
        f'<tr><td class="mono">{escape(e.key)}</td><td class="mono">{escape(e.file)}:{e.line}</td>'
        f'<td><span class="pill {escape(v.replace(" ", "-"))}">{escape(v)}</span></td><td>{escape(notes.get(e.key, ""))}</td></tr>'
        for e, v in rows
    ) or '<tr><td colspan="4" class="muted">No import edges added or removed.</td></tr>'
    state = lambda m: "added" if m in bd.added else "removed" if m in bd.removed else "changed" if m in bd.changed else "context"  # noqa: E731
    details = "\n".join(
        f'<details id="{ids[m]}"><summary><span class="mono">{escape(name(m))}</span> <span class="pill {state(m)}">{state(m)}</span>'
        + (f' <span class="mono muted">+{bd.changed[m][0]} −{bd.changed[m][1]}</span>' if m in bd.changed else "")
        + f'</summary><pre class="diff">{_hunk_html(hunks.get(m, "")) or "No changes in this module."}</pre></details>'
        for m in shown
    )
    chips = [("added", f"+{len(bd.added)} modules"), ("removed", f"−{len(bd.removed)} modules"), ("changed", f"~{len(bd.changed)} changed"),
             ("context", f"+{len(bd.edges_added)} / −{len(bd.edges_removed)} edges"), ("drift", f"{sum(v == 'drift' for v in verdicts.values())} drift")]
    return TEMPLATE.format(
        title=escape(title), subtitle=escape(subtitle), cdn=MERMAID_CDN, mmd=escape(mmd), table=table, details=details,
        chips="".join(f'<span class="pill {c}">{escape(t)}</span>' for c, t in chips),
        rest=f"{rest} untouched modules not drawn." if rest else "",
    )


TEMPLATE = """<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {{
  --bg: #f5f6f8; --surface: #ffffff; --ink: #1b2230; --muted: #5e6878; --rule: #d9dde4; --accent: #2f5bd3;
  --add: #1f8a4c; --add-bg: #e3f4ea; --del: #c23b3b; --del-bg: #fbe8e8; --drift: #c2410c; --drift-bg: #fdebdf; --hdr: #6b56c4;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif; --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  color-scheme: dark; --bg: #12151b; --surface: #1a1f28; --ink: #e4e8ef; --muted: #98a2b3; --rule: #2a313d; --accent: #7aa2ff;
  --add: #4cc27e; --add-bg: #173323; --del: #f07070; --del-bg: #3a1a1c; --drift: #fb923c; --drift-bg: #3a2414; --hdr: #b4a5f5;
}} }}
:root[data-theme="dark"] {{
  color-scheme: dark; --bg: #12151b; --surface: #1a1f28; --ink: #e4e8ef; --muted: #98a2b3; --rule: #2a313d; --accent: #7aa2ff;
  --add: #4cc27e; --add-bg: #173323; --del: #f07070; --del-bg: #3a1a1c; --drift: #fb923c; --drift-bg: #3a2414; --hdr: #b4a5f5;
}}
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
#graph {{ padding: 16px; min-height: 120px; }}
#graph svg {{ max-width: none; }}
table {{ border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
th {{ font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
tr:last-child td {{ border-bottom: 0; }}
.modules {{ display: grid; gap: 8px; }}
details {{ background: var(--surface); border: 1px solid var(--rule); border-radius: 6px; scroll-margin-top: 16px; }}
details[open] {{ border-color: var(--accent); }}
summary {{ cursor: pointer; padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
pre.diff {{ margin: 0; padding: 12px 14px; border-top: 1px solid var(--rule); overflow-x: auto; font: 12.5px/1.5 var(--mono); }}
pre.diff .add {{ color: var(--add); background: var(--add-bg); display: inline-block; min-width: 100%; }}
pre.diff .del {{ color: var(--del); background: var(--del-bg); display: inline-block; min-width: 100%; }}
pre.diff .hdr {{ color: var(--hdr); }}
.legend {{ font-size: .85rem; color: var(--muted); margin: 8px 0 0; }}
</style>
<main>
  <header>
    <h1>{title}</h1>
    <div class="muted mono">{subtitle}</div>
    <div class="chips">{chips}</div>
  </header>
  <section>
    <h2>Module graph</h2>
    <div class="scroll"><div id="graph"></div></div>
    <p class="legend">Green: new module. Red dashed: removed. Blue: changed, with lines +added −removed. Thick arrow: new import. Orange arrow: drift from the import rules. Dashed arrow: import removed. {rest} Click a module to open its diff.</p>
  </section>
  <section>
    <h2>Import edges</h2>
    <div class="scroll"><table><thead><tr><th>Edge</th><th>Created at</th><th>Verdict</th><th>Why</th></tr></thead><tbody>
{table}
    </tbody></table></div>
  </section>
  <section>
    <h2>Modules</h2>
    <div class="modules">
{details}
    </div>
  </section>
</main>
<pre id="mmd" hidden>{mmd}</pre>
<script src="{cdn}"></script>
<script>
(function () {{
  var root = document.documentElement;
  var dark = root.dataset.theme === "dark" || (root.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  function open(id) {{
    var d = document.getElementById(id);
    if (!d) return;
    d.open = true;
    d.scrollIntoView({{ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }});
  }}
  document.getElementById("graph").addEventListener("click", function (ev) {{
    var a = ev.target.closest("a");
    var href = a && (a.getAttribute("href") || a.getAttribute("xlink:href"));
    if (href && href.charAt(0) === "#") {{ ev.preventDefault(); open(href.slice(1)); }}
  }});
  if (!window.mermaid) {{ document.getElementById("graph").textContent = "Mermaid did not load; the diagram source is in the page."; return; }}
  mermaid.initialize({{ startOnLoad: false, securityLevel: "loose", theme: dark ? "dark" : "default", flowchart: {{ htmlLabels: true }} }});
  mermaid.render("g", document.getElementById("mmd").textContent).then(function (r) {{ document.getElementById("graph").innerHTML = r.svg; }});
}})();
</script>
"""
