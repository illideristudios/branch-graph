"""RevisionSource over git: every read is `git ls-tree` / `git show` / `git diff`, never a checkout."""

from __future__ import annotations

import subprocess


class GitSource:
    def __init__(self, repo: str):
        self.repo = repo
        self.repo = self._git("rev-parse", "--show-toplevel").strip()

    def _git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True, text=True, errors="replace").stdout

    def merge_base(self, a: str, b: str) -> str:
        return self._git("merge-base", a, b).strip()

    def short(self, rev: str) -> str:
        return self._git("rev-parse", "--short", rev).strip()

    def files(self, rev: str, root: str) -> list[str]:
        return self._git("ls-tree", "-r", "--name-only", rev, "--", root).splitlines()

    def read(self, rev: str, path: str) -> str:
        return self._git("show", f"{rev}:{path}")

    def numstat(self, base: str, head: str, root: str) -> dict[str, tuple[int, int]]:
        out = {}
        for line in self._git("diff", "--no-renames", "--numstat", base, head, "--", root).splitlines():
            plus, minus, path = line.split("\t", 2)
            out[path] = (int(plus) if plus != "-" else 0, int(minus) if minus != "-" else 0)
        return out

    def hunks(self, base: str, head: str, paths: list[str]) -> str:
        return self._git("diff", "--no-renames", base, head, "--", *paths) if paths else ""
