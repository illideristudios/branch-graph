"""Python: `ast` imports, relative ones resolved, anything outside the revision's own modules dropped."""

from __future__ import annotations

import ast
from pathlib import PurePosixPath
from typing import Iterator

ModuleId = tuple[str, ...]


def _longest_known(parts: ModuleId, known: set[ModuleId]) -> ModuleId | None:
    return next((parts[:i] for i in range(len(parts), 0, -1) if parts[:i] in known), None)


class PythonModule:
    name = "python"

    def claims(self, path: str) -> bool:
        return path.endswith(".py")

    def module_of(self, path: str, root: str, source: str = "") -> ModuleId | None:
        rel = PurePosixPath(path).relative_to(root) if root not in ("", ".") else PurePosixPath(path)
        parts = rel.with_suffix("").parts
        return parts[:-1] if parts[-1] == "__init__" else parts

    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterator[tuple[ModuleId, int]]:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            return
        package = module if path.endswith("__init__.py") else module[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                targets = [tuple(a.name.split(".")) for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = package[: len(package) - node.level + 1] if node.level else ()
                base += tuple(node.module.split(".")) if node.module else ()
                targets = [base + (a.name,) for a in node.names]
            else:
                continue
            for target in targets:
                if (hit := _longest_known(target, known)) is not None:
                    yield hit, node.lineno


MODULE = PythonModule()
