"""RevisionSource over git: every read is `git ls-tree` / `git show` / `git diff`, never a checkout."""

from __future__ import annotations

import re
import subprocess

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class GitSource:
    def __init__(self, repo: str):
        self.repo = repo
        self.repo = self._git("rev-parse", "--show-toplevel").strip()

    def _git(self, *args: str) -> str:
        """`core.quotePath=false` keeps non-ASCII names readable in diff headers; path lists use `-z` besides."""
        return subprocess.run(["git", "-C", self.repo, "-c", "core.quotePath=false", *args], check=True, capture_output=True, text=True,
                              errors="replace").stdout

    def merge_base(self, a: str, b: str) -> str:
        return self._git("merge-base", a, b).strip()

    def short(self, rev: str) -> str:
        return self._git("rev-parse", "--short", rev).strip()

    def rev(self, rev: str) -> str:
        return self._git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def files(self, rev: str, root: str) -> list[str]:
        return [p for p in self._git("ls-tree", "-r", "-z", "--name-only", rev, "--", root).split("\0") if p]

    def read_all(self, rev: str, paths: list[str]) -> dict[str, str]:
        """One `git cat-file --batch` for all of them: a `git show` each costs ~17 ms, which is minutes on a PHP tree.
        A path with no blob at `rev` reads as empty."""
        if not paths:
            return {}
        request = "".join(f"{rev}:{p}\n" for p in paths).encode()
        data = subprocess.run(["git", "-C", self.repo, "cat-file", "--batch"], input=request, check=True, capture_output=True).stdout
        out, pos = {}, 0
        for path in paths:
            eol = data.index(b"\n", pos)
            header = data[pos:eol].split()
            if header[-1] == b"missing":
                out[path], pos = "", eol + 1
            else:
                start = eol + 1
                size = int(header[2])
                out[path], pos = data[start : start + size].decode(errors="replace"), start + size + 1
        return out

    def numstat(self, base: str, head: str, root: str) -> dict[str, tuple[int, int]]:
        out = {}
        for record in filter(None, self._git("diff", "--no-renames", "--numstat", "-z", base, head, "--", root).split("\0")):
            plus, minus, path = record.split("\t", 2)
            out[path] = (int(plus) if plus != "-" else 0, int(minus) if minus != "-" else 0)
        return out

    def hunks(self, base: str, head: str, paths: list[str]) -> str:
        return self._git("diff", "--no-renames", base, head, "--", *paths) if paths else ""

    def changed_lines(self, base: str, head: str, root: str) -> dict[str, tuple[set[int], set[int]]]:
        """{path: (base lines removed or changed, head lines added or changed)}, from a zero-context diff."""
        out: dict[str, tuple[set[int], set[int]]] = {}
        lines = None
        for line in self._git("diff", "--no-renames", "-U0", base, head, "--", root).splitlines():
            if line.startswith("diff --git a/"):
                both = line[len("diff --git a/"):]
                lines = out.setdefault(both[: (len(both) - 3) // 2], (set(), set()))
            elif lines is not None and (h := HUNK.match(line)):
                a, b, c, d = int(h[1]), int(h[2] or 1), int(h[3]), int(h[4] or 1)
                lines[0].update(range(a, a + b))
                lines[1].update(range(c, c + d))
        return out
