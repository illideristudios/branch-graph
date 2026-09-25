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
        for line in self._git("diff", "--no-renames", "--numstat", base, head, "--", root).splitlines():
            plus, minus, path = line.split("\t", 2)
            out[path] = (int(plus) if plus != "-" else 0, int(minus) if minus != "-" else 0)
        return out

    def hunks(self, base: str, head: str, paths: list[str]) -> str:
        return self._git("diff", "--no-renames", base, head, "--", *paths) if paths else ""
