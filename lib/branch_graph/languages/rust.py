"""Rust: a file's module is its crate plus its path under `src/`, and `use` trees name modules.

The crate is the directory holding the file's nearest `src/` (else its `tests/`, `benches/` or `examples/`), hyphens read
as underscores. `lib.rs` and `main.rs` are the crate itself, a `mod.rs` is its directory, and `build.rs` is not a module.
A `src/bin/` binary and a test, bench or example target are crates of their own to `crate::`.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Iterator

from . import _braces

ModuleId = tuple[str, ...]

TREES = ("src", "tests", "benches", "examples")
USE = re.compile(r"(?:^|[;{}])\s*(?:pub(?:\([^)]*\))?\s+)?(use)\s+([^;]+);", re.M)
TYPE = re.compile(r"^[ \t]*(?:pub(?:\([^)\n]*\))?[ \t]+)?(?:unsafe[ \t]+)?(?:struct|enum|union|trait)[ \t]+([A-Za-z_]\w*)", re.M)
IMPL = re.compile(r"^[ \t]*(?:unsafe[ \t]+)?impl\b([^{;]*)", re.M)
MOD = re.compile(r"^[ \t]*(?:pub(?:\([^)\n]*\))?[ \t]+)?mod[ \t]+([A-Za-z_]\w*)", re.M)

# Raw strings, strings, chars, lifetimes, comments and attributes, matched left to right so none starts inside another.
# A `/*` is closed by _blank's count, since Rust block comments nest.
TOKEN = re.compile(
    r'\bb?r(#*)"[\s\S]*?"\1|b?"(?:\\.|[^"\\])*"'
    r"|b?'(?:\\(?:u\{\w*\}|x\w\w|.)|[^'\\\n])'|'[A-Za-z_]\w*"
    r'|//[^\n]*|#!?\[(?:"(?:\\.|[^"\\])*"|[^\]"\n])*\]|/\*'
)
COMMENT = re.compile(r"/\*|\*/")


# ponytail: a lexer in one regex, not a parser. A `c"…"` or `cr"…"` C string with escapes, or an attribute that holds a
# `]` outside a string, can still misplace a brace. Upgrade path: tree-sitter-rust, if attribution looks wrong in review.
def _blank(source: str) -> str:
    """The source with strings, chars, lifetimes, comments and attributes blanked, line numbers kept."""
    out, i = [], 0
    while m := TOKEN.search(source, i):
        end = m.end()
        if m.group(0) == "/*":
            depth, end = 1, len(source)
            for c in COMMENT.finditer(source, m.end()):
                depth += 1 if c.group(0) == "/*" else -1
                if depth == 0:
                    end = c.end()
                    break
        out += [source[i : m.start()], re.sub(r"[^\n]", " ", source[m.start() : end])]
        i = end
    return "".join(out) + source[i:]


def _expand(tree: str) -> list[ModuleId]:
    """`a::{b, c::{d, e}}` -> [a.b, a.c.d, a.c.e], for a tree with whitespace and `as` aliases already removed."""
    i = tree.find("{")
    if i < 0:
        return [tuple(s for s in tree.split("::") if s)]
    prefix = tuple(s for s in tree[:i].split("::") if s)
    inner, items, depth, start = tree[i + 1 : tree.rindex("}")], [], 0, 0
    for j, ch in enumerate(inner):
        depth += (ch == "{") - (ch == "}")
        if ch == "," and depth == 0:
            items.append(inner[start:j])
            start = j + 1
    items.append(inner[start:])
    return [prefix + path for item in items if item for path in _expand(item)]


def _longest_known(parts: ModuleId, known: set[ModuleId]) -> ModuleId | None:
    return next((parts[:i] for i in range(len(parts), 0, -1) if parts[:i] in known), None)


def _locate(parts: tuple[str, ...]) -> int | None:
    """The index of the tree a file's crate path starts below: its last `src/`, else its first test, bench or example."""
    dirs = parts[:-1]
    src = [i for i, s in enumerate(dirs) if s == "src"]
    return src[-1] if src else next((i for i, s in enumerate(dirs) if s in TREES), None)


def _crate_len(parts: tuple[str, ...]) -> int:
    """How many leading segments of a file's module are its crate: 3 for a binary or target (`app.bin.tool`), else 1."""
    i = _locate(parts)
    if i is None:
        return 1
    below = parts[i + 1 :]
    return 3 if parts[i] != "src" or (below[0] == "bin" and len(below) > 1) else 1


def _impl_name(header: str) -> str:
    """The type an `impl` header implements: `<T: A<B>> Show for path::Wrapper<T> where …` -> `Wrapper`."""
    header, depth, rest = header.replace("->", "  "), 0, header
    for i, ch in enumerate(header):
        depth += (ch == "<") - (ch == ">")
        if depth == 0 and not ch.isspace():
            rest = header[i + 1 :] if ch == ">" else header[i:]
            break
    target = re.split(r"\bfor\b", re.split(r"\bwhere\b", rest)[0])[-1]
    m = re.match(r"[\s&*]*(?:(?:mut|const|dyn)\s+)*(?:\w+::)*(\w+)", target)
    return m.group(1) if m else target.strip()


class RustModule:
    name = "rust"

    def claims(self, path: str) -> bool:
        return path.endswith(".rs")

    # ponytail: the crate is named after its directory ("crate" at the root), not Cargo.toml's `[package] name`; a crate
    # whose name differs from its folder misses the edges into it. Upgrade path: `cargo metadata --format-version 1`.
    def module_of(self, path: str, root: str, source: str = "") -> ModuleId | None:
        p = PurePosixPath(path)
        if p.name == "build.rs":
            return None
        parts = (p.relative_to(root) if root not in ("", ".") else p).with_suffix("").parts
        i = _locate(parts)
        if i is None:
            return parts[:-1] if parts[-1] == "mod" and len(parts) > 1 else parts
        crate = (parts[i - 1] if i else PurePosixPath(root).name or "crate").replace("-", "_")
        tree, below = parts[i], parts[i + 1 :]
        if tree == "src" and below in (("lib",), ("main",)):
            return (crate,)
        if below[-1] == "mod" or (below[-1] == "main" and len(below) > 1 and (tree != "src" or below[0] == "bin")):
            below = below[:-1]
        return (crate,) + (below if tree == "src" else (tree,) + below)

    # ponytail: `use` declarations only, not inline paths (`crate::x::f()`) or `extern crate`. Upgrade path: scan bodies
    # for `crate::`/`super::` paths too, if reviews show edges missing.
    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterator[tuple[ModuleId, int]]:
        text = _blank(source)
        mods = _braces.ranges(source, MOD, _blank)
        crate = module[: _crate_len(PurePosixPath(path).with_suffix("").parts)]
        for m in USE.finditer(text):
            tree = re.sub(r"\s+", "", re.sub(r"\s+as\s+\w+", "", m.group(2)))
            line = text.count("\n", 0, m.start(1)) + 1
            # An inline `mod tests { … }` sits one level below the file's module, for `super::` and `self::`.
            here = module + tuple(name for name, first, last in mods if first <= line <= last)
            for parts in _expand(tree):
                parts = parts[:1] + tuple(s for s in parts[1:] if s not in ("self", "*"))
                if not parts:
                    continue
                # (path, shortest acceptable hit): a path relative to this module must land below it.
                if parts[0] == "crate":
                    tries = [(crate + parts[1:], 1)]
                elif parts[0] == "super":
                    n = next((i for i, s in enumerate(parts) if s != "super"), len(parts))
                    tries = [(here[: max(len(here) - n, 1)] + parts[n:], 1)]
                elif parts[0] == "self":
                    tries = [(here + parts[1:], len(here) + 1)]
                elif tree.startswith("::"):
                    tries = [(parts, 1)]
                else:
                    # 2018 uniform paths: a child module of this one first, else another crate.
                    tries = [(here + parts, len(here) + 1), (parts, 1)]
                    if len(crate) == 3 and crate[0] == "crate" and parts[0] not in ("std", "core", "alloc"):
                        # A root crate's binaries and tests name its library by a package name module_of cannot see.
                        tries.append((crate[:1] + parts[1:], 2))
                for cand, floor in tries:
                    hit = _longest_known(cand, known)
                    if hit and len(hit) >= floor and hit != module:
                        yield hit, line
                        break

    def classes(self, source: str) -> list[tuple[str, int, int]]:
        impls = [(_impl_name(header), first, last) for header, first, last in _braces.ranges(source, IMPL, _blank)]
        return sorted(_braces.ranges(source, TYPE, _blank) + impls, key=lambda r: r[1])


MODULE = RustModule()
