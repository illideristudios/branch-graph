"""PHP: a file's namespace + filename is its module (PSR-4: class name = filename), else its path under the root.

Edges are `use` statements, matched exactly against a module: a `use` names a class, never a package.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Iterator

ModuleId = tuple[str, ...]

NAMESPACE = re.compile(r"^[ \t]*namespace[ \t]+([\w\\]+)[ \t]*[;{]", re.M)
USE = re.compile(r"^[ \t]*use[ \t]+(?!function\b|const\b)([\w\\ \t,]+?)\s*(?:\{([^}]*)\})?\s*;", re.M)
ALIAS = re.compile(r"\s+as\s+\w+$")


def _names(prefix: str, group: str | None) -> Iterator[str]:
    base, items = ("", prefix.split(",")) if group is None else (prefix.strip(), group.split(","))
    for item in items:
        item = ALIAS.sub("", item.strip())
        if item and not item.startswith(("function ", "const ")):
            yield (base + item).lstrip("\\")


class PhpModule:
    name = "php"

    def claims(self, path: str) -> bool:
        return path.endswith(".php")

    def module_of(self, path: str, root: str, source: str = "") -> ModuleId | None:
        stem = PurePosixPath(path).with_suffix("")
        if ns := NAMESPACE.search(source):
            return (*ns.group(1).split("\\"), stem.name)
        return (stem.relative_to(root) if root not in ("", ".") else stem).parts

    # ponytail: regex, not a parser. Misses `use function/const`, `require`/`include` (their paths are runtime values),
    # a class whose name differs from its filename, and a second namespace in one file; matches a `use` line inside a
    # /* */ block. Also misses inline \Fq\Names with no `use`: on the OpenEMR fork that is +55% file-level edges but
    # only +2% module edges at depth 2 (869 -> 892), so the diagram barely moves. Upgrade path: a tokenizer, if reviews
    # show misses.
    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterator[tuple[ModuleId, int]]:
        for m in USE.finditer(source):
            line = source.count("\n", 0, m.start()) + 1
            for name in _names(m.group(1), m.group(2)):
                if "\\" in name and (target := tuple(name.split("\\"))) in known:
                    yield target, line


MODULE = PhpModule()
