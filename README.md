# branch-graph

Draws a branch's diff as a before/after module import diagram — every module
linked to the hunks that changed it, every new import edge linked to the
`file:line` that created it — and checks new imports against an
`import-rules` block, flagging drift. Languages plug in as modules under
`lib/branch_graph/languages/`; Python, PHP and Swift ship. `--json` writes a
machine-readable summary and `--fail-on-drift` exits 1 on a drift verdict.
Optional `lizard`/`radon` add complexity, duplication and coverage metrics as
branch deltas.

## Story

Approved for addition and enabling on 2026-09-23. The approval ledger
(`SETUP-LIST.md` in
[locriani/ai-additions](https://github.com/locriani/ai-additions)) records
the row verbatim:

> ```
> | `branch-graph` | 2026-09-23 | "branch-graph is approved for addition and enabling" (Zach, 18:42) | **Yes** — enabled by the same phrase; installed from the local marketplace once merged — installed 2026-09-23 20:15 CT on "merged, install it" (PR 3), 0.1.0 at user scope; 22/22 on main at 4d06e06; updated to **0.5.0** on 2026-09-26 at 14:2x CT on "commit / merge / install" after PR 15 (complexity, duplication and coverage metrics as branch deltas; 0.2.0–0.4.0 came through PRs 12–14, and 0.4.0 was installed by the chief-of-stuff-improvements session). 105 tests OK on main at 8ebc9d5 |
> ```

## Provenance

Extracted 2026-10-10 from
[locriani/ai-additions](https://github.com/locriani/ai-additions) at commit
`a01d7eb87d3d24b1cd65bcf509eed82000f7fa21` (plugin history: `git log` in
that repo, path `plugins/branch-graph`). The carried history spans 0.1.0
through 0.6.0, authorship preserved. Content is verbatim except one
cross-reference fix: the skill's render-check step now names the
`mermaid-system-design` plugin from its own marketplace (it previously
resolved through the umbrella's plugin cache path) and documents a fallback
when that plugin is not installed.

## Install

```bash
claude plugin marketplace add locriani/branch-graph
claude plugin install branch-graph@branch-graph
```

Update: `claude plugin marketplace update branch-graph`, then reinstall.

## Layout

| Path | What it is |
| --- | --- |
| `bin/branch-graph` | The CLI (`python3`). |
| `lib/branch_graph/` | The library: domain, ports, use case, renderers, `languages/` (Python, PHP, Swift), `providers/` (lizard, radon). |
| `skills/branch-graph/` | `SKILL.md` — how a review runs the tool and reads the page. |
| `tests/` | Stdlib `unittest` suite. |

## Development

Runtime: `python3` (stdlib) and `git` — the tool reads both revisions
through `git`, so it works against any repo with a diffable base. The
optional metric providers (`lizard`, `radon`) enrich the page and unskip
their tests.

## Tests

```bash
python3 -m unittest discover -s tests
```

Without `lizard`/`radon` importable, the metric-provider tests skip — and a
skipped test is not a pass — so CI installs pinned versions
(`lizard==1.24.1`, `radon==6.0.1`) and runs the same discovery command
(`.github/workflows/tests.yml`: push-only, `contents: read`, checkout pinned
to a commit SHA with `persist-credentials: false`, git-capable `python:3.14`
container).

## License

MIT — see [LICENSE](LICENSE).
