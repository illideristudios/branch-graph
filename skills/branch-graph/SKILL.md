---
name: branch-graph
description: Use when a branch or pull request is opened, or when someone asks for a picture of a branch, a module-level review, or "what did this change touch" — draws the branch's diff as a before/after module import diagram, one click from each module to its hunks, and flags new imports the architecture's rules do not allow. Do NOT use for runtime call graphs or for charts of data.
---

# branch-graph

Draws a branch's diff at module level: modules added (green), removed (red, dashed) and changed (`+N −M` lines), import edges added (thick) and removed (dashed), and drift (orange) where an `import-rules` block exists and no rule allows a new edge. Each module links to its own `git diff` hunks on the page. It reads both revisions with `git ls-tree` and `git cat-file`, so nothing is checked out.

The tool is `bin/branch-graph` two levels above this skill's base directory. Languages are modules in `lib/branch_graph/languages/`; Python and PHP ship.

## Steps

1. **Run it.**

   ```
   python3 <base>/../../bin/branch-graph --repo <repo> --root <import root> --depth 2 --out <scratch>/page.html
   ```

   - `--base` defaults to `git merge-base origin/main HEAD`, and `--head` to `HEAD`. For a merged PR, pass `--base <merge>^1 --head <merge>^2`.
   - `--root` is the directory imports are resolved from (`agent` in the OpenEMR fork, `scripts` in chief-of-stuff).
   - `--depth` is how many module segments make one box: 2 for a packaged tree, 1 for a flat one.
   - PHP: a file is named by its `namespace` plus filename, or by its path under `--root` when it declares none. So `--root .` shows legacy code using namespaced code, and `--depth 2` gives vendor + package (`OpenEMR.Common`). Mermaid draws at most 500 edges: on the OpenEMR fork `--root .` draws 272 boxes and 561 edges and the render-check fails, while `--root src` draws 34 and 90. When the check fails, narrow `--root`. Edges are `use` statements matched exactly, not `require`/`include`, `use function`, or inline `\Fq\Names` (on the OpenEMR fork the last is +2% module edges at depth 2).
   - `--rules ARCHITECTURE.md` reads the first ```` ```import-rules ```` fence (one `A -> B` glob pair per line). With no fence, every verdict is `no rules`. Never write rules into a file to get a verdict.

   Stdout is one summary line (`nodes +a −r ~c edges +e −x drift=d`), then one line per new edge with the `file:line` that created it.

2. **Write the notes.** For each new edge, one line on why it exists, read from the code at that `file:line`, into a JSON file: `{"app.web -> app.rag": "the chat route streams retrieved passages"}`.

3. **Run it again** with `--notes <that file>`, so the why column is filled.

4. **Render-check.** Run `mermaid-check.py <scratch>/page.mmd` (from `mermaid-system-design`: the newest `~/.claude/plugins/cache/ai-additions/mermaid-system-design/*/skills/mermaid-system-design/scripts/mermaid-check.py`). It must exit 0. A diagram that did not render is not published.

5. **Publish** `page.html` with the Artifact tool, and put the link in the pull request body. For a PR opened before the page existed, add the link with `gh pr edit <n> --body-file`.

## Reading it

- A new edge into a module nobody expected is the review's first question, whatever the verdict.
- `drift` is a rule check, not a judgement. The finding is the edge and its `file:line`; whether the rule or the code is wrong is the reviewer's call.
- Modules one hop from a touched one are drawn for context, and only edges with a touched end are drawn. The count of undrawn modules is on the page.
