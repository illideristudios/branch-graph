"""Swift: a file's module is its target, and `import` lines name targets directly.

The target is the directory under `Sources/` or `Tests/` (SwiftPM), else the first directory under the root (an Xcode
target folder). Every file of a target is one module: Swift files in a target never import each other.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Iterator

from . import _braces

ModuleId = tuple[str, ...]

TYPE = re.compile(r"\b(?:class|struct|enum|extension|actor|protocol)[ \t]+(?!func\b|var\b|let\b)([A-Za-z_][\w.]*)")
IMPORT = re.compile(
    r"^[ \t]*(?:(?:@\w+(?:\([^)\n]*\))?|public|package|internal|fileprivate|private)[ \t]+)*"
    r"import[ \t]+(?:(?:typealias|struct|class|enum|protocol|let|var|func)[ \t]+)?(\w+)",
    re.M,
)


class SwiftModule:
    name = "swift"

    def claims(self, path: str) -> bool:
        return path.endswith(".swift")

    # ponytail: directory layout, not Package.swift or the .xcodeproj. Misses a target with a custom `path:`, and an Xcode
    # target whose folder is not first under the root. Upgrade path: `swift package describe --type json` for SwiftPM.
    def module_of(self, path: str, root: str, source: str = "") -> ModuleId | None:
        p = PurePosixPath(path)
        if p.name == "Package.swift" or p.name.startswith("Package@swift-"):
            return None
        for i, part in enumerate(p.parts[:-2]):
            if part in ("Sources", "Tests"):
                return (p.parts[i + 1],)
        rel = p.relative_to(root) if root not in ("", ".") else p
        return rel.parts[:1] if len(rel.parts) > 1 else (rel.stem,)

    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterator[tuple[ModuleId, int]]:
        for m in IMPORT.finditer(source):
            if (target := (m.group(1),)) in known:
                yield target, source.count("\n", 0, m.start()) + 1

    def classes(self, source: str) -> list[tuple[str, int, int]]:
        return _braces.ranges(source, TYPE)


MODULE = SwiftModule()
