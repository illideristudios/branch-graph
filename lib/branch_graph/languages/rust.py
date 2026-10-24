"""Rust: a file's module is its crate plus its path under `src/`, and `use` trees name modules.

The crate is named by its Cargo.toml (`[lib] name`, else `[package] name`), else by the directory holding the file's
nearest `src/` (else its `tests/`, `benches/` or `examples/`); hyphens read as underscores. `lib.rs` and `main.rs` are
the crate itself, a `mod.rs` is its directory, and `build.rs` is not a module. A `src/bin/` binary and a test, bench or
example target are crates of their own to `crate::`.
"""

from __future__ import annotations

import re
import tomllib
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
    close = tree.rfind("}")  # missing in a file that does not compile; read to the end rather than fail the run
    inner, items, depth, start = tree[i + 1 : close if close > i else len(tree)], [], 0, 0
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


def _crate(parts: tuple[str, ...], module: ModuleId) -> tuple[ModuleId, bool]:
    """The module `crate::` names in a file, and whether the file is that crate's root file, whose `mod`s are siblings.

    `tests/smoke.rs` is the root of crate `app.tests` (so `mod common;` is `tests/common/mod.rs`); `tests/e2e/main.rs`
    and the files beside it are crate `app.tests.e2e`; `src/bin/` binaries follow the same rule one level down.
    """
    i = _locate(parts)
    if i is None:
        return module[:1], False
    tree, below = parts[i], parts[i + 1 :]
    if tree == "src" and (below[0] != "bin" or len(below) == 1):
        return module[:1], False
    if len(below) == (2 if tree == "src" else 1):
        return module[:2], True
    return module[:3], False


def _crate_name(manifest: str) -> str | None:
    """The name a Cargo.toml's crate is imported by: `[lib] name`, else `[package] name`; None for a workspace root."""
    try:
        data = tomllib.loads(manifest)
    except tomllib.TOMLDecodeError:
        return None
    name = data.get("lib", {}).get("name") or data.get("package", {}).get("name")
    return name if isinstance(name, str) else None


def _impl_name(header: str) -> str:
    """The type an `impl` header implements: `<T: A<B>> Show for path::Wrapper<T> where …` -> `Wrapper`."""
    header, depth, rest = header.replace("->", "  "), 0, header
    for i, ch in enumerate(header):
        depth += (ch == "<") - (ch == ">")
        if depth == 0 and not ch.isspace():
            rest = header[i + 1 :] if ch == ">" else header[i:]
            break
    head = re.split(r"\bwhere\b", rest)[0]
    # The trait's `for`, not a higher-ranked `for<'a>` nested inside the type's generics.
    cuts = [m.end() for m in re.finditer(r"\bfor\b", head) if head[: m.start()].count("<") == head[: m.start()].count(">")]
    target = head[cuts[-1] :] if cuts else head
    m = re.match(r"[\s&*]*(?:(?:mut|const|dyn)\s+)*(?:\w+::)*(\w+)", target)
    return m.group(1) if m else target.strip()


class RustModule:
    name = "rust"
    manifest = "Cargo.toml"

    def __init__(self, names: dict[str, str] | None = None):
        self.names = names or {}  # crate directory -> the name its Cargo.toml gives it

    def configured(self, manifests: dict[str, str]) -> RustModule:
        """A copy that names each crate by its Cargo.toml rather than its folder."""
        return RustModule({str(PurePosixPath(p).parent): n for p, text in manifests.items() if (n := _crate_name(text))})

    def claims(self, path: str) -> bool:
        return path.endswith(".rs")

    # ponytail: a crate's directory is found from the standard layout, not Cargo.toml's `[lib] path` or `[[bin]] path`;
    # a crate with custom source paths is named by folder. Upgrade path: `cargo metadata --format-version 1`.
    def module_of(self, path: str, root: str, source: str = "") -> ModuleId | None:
        p = PurePosixPath(path)
        if p.name == "build.rs":
            return None
        full = p.with_suffix("").parts
        i = _locate(full)
        if i is None:
            parts = (p.relative_to(root) if root not in ("", ".") else p).with_suffix("").parts
            return parts[:-1] if parts[-1] == "mod" and len(parts) > 1 else parts
        crate = (self.names.get("/".join(full[:i]) or ".") or (full[i - 1] if i else "crate")).replace("-", "_")
        tree, below = full[i], full[i + 1 :]
        if tree == "src" and below in (("lib",), ("main",)):
            return (crate,)
        if below[-1] == "mod" or (below[-1] == "main" and len(below) > 1 and (tree != "src" or below[0] == "bin")):
            below = below[:-1]
        return (crate,) + (below if tree == "src" else (tree,) + below)

    # ponytail: `use` declarations only, not inline paths (`crate::x::f()`) or `extern crate`. Upgrade path: scan bodies
    # for `crate::`/`super::` paths too, if reviews show edges missing.
    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterator[tuple[ModuleId, int]]:
        text = _blank(source)
        mods = _braces.ranges(text, MOD, str)
        crate, root_file = _crate(PurePosixPath(path).with_suffix("").parts, module)
        for m in USE.finditer(text):
            tree = re.sub(r"\s+", "", re.sub(r"\s+as\s+\w+", "", m.group(2))).replace("r#", "")
            line = text.count("\n", 0, m.start(1)) + 1
            # An inline `mod tests { … }` sits one level below the file's module, for `super::` and `self::`.
            here = (crate if root_file else module) + tuple(name for name, first, last in mods if first <= line <= last)
            for parts in _expand(tree):
                parts = parts[:1] + tuple(s for s in parts[1:] if s not in ("self", "*"))
                if not parts:
                    continue
                # (path, shortest acceptable hit): a relative path must land below this module, and none leaves the crate.
                if parts[0] == "crate":
                    tries = [(crate + parts[1:], len(crate))]
                elif parts[0] == "super":
                    n = next((i for i, s in enumerate(parts) if s != "super"), len(parts))
                    tries = [(here[: max(len(here) - n, 1)] + parts[n:], len(crate))]
                elif parts[0] == "self":
                    tries = [(here + parts[1:], len(here) + 1)]
                elif tree.startswith("::"):
                    tries = [(parts, 1)]
                else:
                    # 2018 uniform paths: a child module of this one first, else another crate.
                    tries = [(here + parts, len(here) + 1), (parts, 1)]
                for cand, floor in tries:
                    hit = _longest_known(cand, known)
                    if hit and len(hit) >= floor and hit != module:
                        yield hit, line
                        break

    def classes(self, source: str) -> list[tuple[str, int, int]]:
        text = _blank(source)
        impls = [(_impl_name(header), first, last) for header, first, last in _braces.ranges(text, IMPL, str)]
        return sorted(_braces.ranges(text, TYPE, str) + impls, key=lambda r: r[1])


MODULE = RustModule()
