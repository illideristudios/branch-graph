---
name: branch-graph
description: Use when a branch or pull request is opened, or when someone asks for a picture of a branch, a module-level review, or "what did this change touch" — draws the branch's diff as a before/after module import diagram, one click from each module to its hunks, and flags new imports the architecture's rules do not allow. Do NOT use for runtime call graphs or for charts of data.
---

# branch-graph

Draws a branch's diff at module level: modules added (green), removed (red, dashed) and changed (`+N −M` lines), import edges added (thick) and removed (dashed), and drift (orange) where an `import-rules` block exists and no rule allows a new edge. Clicking a module highlights its imports; its panel lists every connection both ways and its diff, file by file with line numbers. Every arrow and every edge row links to the line that created it. It reads both revisions with `git ls-tree` and `git cat-file`, so nothing is checked out.

The tool is `bin/branch-graph` two levels above this skill's base directory. Languages are modules in `lib/branch_graph/languages/`; Python, PHP and Swift ship.

## Steps

1. **Run it.**

   ```
   python3 <base>/../../bin/branch-graph --repo <repo> --root <import root> --depth 2 --out <scratch>/page.html
   ```

   - `--base` defaults to `git merge-base origin/main HEAD`, and `--head` to `HEAD`. For a merged PR, pass `--base <merge>^1 --head <merge>^2`.
   - `--root` is the directory imports are resolved from (`agent` in the OpenEMR fork, `scripts` in chief-of-stuff).
   - `--depth` is how many module segments make one box: 2 for a packaged tree, 1 for a flat one.
   - PHP: a file is named by its `namespace` plus filename, or by its path under `--root` when it declares none. So `--root .` shows legacy code using namespaced code, and `--depth 2` gives vendor + package (`OpenEMR.Common`). Edges are `use` statements matched exactly, not `require`/`include`, `use function`, or inline `\Fq\Names` (on the OpenEMR fork the last is +2% module edges at depth 2).
   - Swift: a file belongs to its target (the directory under `Sources/` or `Tests/`, else the first directory under `--root`), and `import` lines name targets; system frameworks are dropped. `Package.swift` is not a module.
   - `--exclude GLOB` (repeatable) drops every module whose collapsed name matches, with its edges and diffs, before anything is drawn or counted: `--exclude 'tests.*' --exclude 'evals.*'`.
   - `--max-nodes N` (at least 3) splits the drawing into views of at most N modules each, written as `page-1.mmd`…`page-K.mmd` instead of `page.mmd`, all shown on `page.html`. Each touched module belongs to one view; a view grows through its touched neighbours, and a touched module drawn in another view's context is labelled `in view k`. Unrelated clusters are always separate views.
   - `--rules ARCHITECTURE.md` reads the first ```` ```import-rules ```` fence (one `A -> B` glob pair per line). With no fence, every verdict is `no rules`. Never write rules into a file to get a verdict.
   - `--json PATH` writes a machine-readable summary with full base/head commit SHAs, added/removed/changed nodes, new edges with verdicts, removed edges with no verdict, drift count, excluded count and view count.
   - `--fail-on-drift` needs a `--rules` file that holds an `import-rules` block and exits 1 when a new import has the verdict `drift`; the page and output are still written.

   - `--colors colors.json` overrides the palette, for the page and the diagram alike: `{"light": {"add": "#1f8a4c"}, "dark": {"bg": "#000000"}}`. The tokens are `bg surface ink muted rule edge accent accent-bg add add-bg del del-bg drift drift-bg hdr`; an unknown token, or a value holding `;`, `:`, braces, quotes or angle brackets, is a usage error. With `--max-nodes` it colors every view.
   - **Metrics** come from optional libraries in the Python that runs the tool (`lizard`: complexity, lines and parameters per function, plus duplication; `radon`: Python maintainability index). Without them the page says what to install and still shows coverage. Only functions whose lines the branch changed are scored, before → after, grouped by class in each module's panel; each module's box gets a line such as `cx +3 · cov 62% · dup 1`.
   - `--coverage REPORT` (repeatable) reads a Cobertura, Clover or LCOV report of the head revision (`coverage xml`, `coverage lcov`, PHPUnit `--coverage-cobertura`/`--coverage-clover`, `llvm-cov export -format=lcov`). Branch-graph never runs tests. Module coverage is diff coverage: the share of changed, executable lines that ran. Function coverage covers the function's whole body.
   - `--dup-scope changed|modules|root` is where copies of changed code are looked for; the default `modules` scans the files of every module the branch touched. `root` is thorough but slow: the whole OpenEMR tree takes 92 s.

   Stdout is one summary line (`nodes +a −r ~c edges +e −x drift=d`, plus ` excluded=n` with `--exclude` and ` views=k` with `--max-nodes`), then one line per new edge with the `file:line` that created it.

2. **Write the notes.** For each new edge, one line on why it exists, read from the code at that `file:line`, into a JSON file: `{"app.web -> app.rag": "the chat route streams retrieved passages"}`.

3. **Run it again** with `--notes <that file>`, so the why column is filled.

4. **Render-check.** Run `mermaid-check.py <scratch>/page.mmd` (each `page-K.mmd` with `--max-nodes`) (from `mermaid-system-design`: the newest `~/.claude/plugins/cache/ai-additions/mermaid-system-design/*/skills/mermaid-system-design/scripts/mermaid-check.py`). It must exit 0. A diagram that did not render is not published.

5. **Publish** `page.html` with the Artifact tool, and put the link in the pull request body. For a PR opened before the page existed, add the link with `gh pr edit <n> --body-file`.

## Reading it

- A new edge into a module nobody expected is the review's first question, whatever the verdict.
- Complexity is lizard's cyclomatic count, the stand-in for flog. A `cx +N` on a box is the change in the summed complexity of its touched functions, and red cells mean a number went up. "Duplication written" counts clones with at least one copy on a line the branch added or changed, the stand-in for flay.
- `drift` is a rule check, not a judgement. The finding is the edge and its `file:line`; whether the rule or the code is wrong is the reviewer's call.
- Modules one hop from a touched one are drawn for context, most-connected first, until 150 edges are drawn; only edges with a touched end are drawn. The count of undrawn modules is on the page. On the OpenEMR fork `--root .` wanted 561 edges and now draws 148. Touched modules are always drawn, so if the render-check still fails or the picture is too dense, `--exclude` what the review does not need, split it with `--max-nodes`, or narrow `--root`.
