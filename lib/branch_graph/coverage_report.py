"""Coverage reports, read: Cobertura XML (coverage.py, PHPUnit, most CI), Clover XML (PHPUnit), LCOV (coverage.py,
llvm-cov for Swift). branch-graph never runs tests; it reads what they left behind."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

Coverage = dict[str, dict[int, int]]


def resolve(reported: str, known: list[str]) -> str | None:
    """The repo path a report means: the one sharing the longest tail of path segments with it, if only one does.
    Reports hold absolute paths, paths under a <source>, or paths relative to wherever the tests ran."""
    tail = PurePosixPath(reported.replace("\\", "/")).parts
    best, score, tie = None, 0, False
    for path in known:
        parts = PurePosixPath(path).parts
        n = 0
        while n < min(len(parts), len(tail)) and parts[-1 - n] == tail[-1 - n]:
            n += 1
        if n > score:
            best, score, tie = path, n, False
        elif n == score and n:
            tie = True
    return None if tie else best


def _add(out: Coverage, path: str | None, line: int, hits: int) -> None:
    if path is not None:
        out.setdefault(path, {})[line] = max(hits, out.get(path, {}).get(line, 0))


def read(report: Path, known: list[str]) -> Coverage:
    """{repo path: {line: hits}} for every file of `report` that is one of `known`. ValueError when it is none of the formats."""
    text = report.read_text(errors="replace")
    out: Coverage = {}
    if text.lstrip().startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError as e:
            raise ValueError(f"coverage: {report} is not a Cobertura, Clover or LCOV report ({e})") from None
        if root.find(".//class[@filename]") is not None:
            for cls in root.iter("class"):
                path = resolve(cls.get("filename", ""), known)
                for line in cls.iter("line"):
                    _add(out, path, int(line.get("number", 0)), int(line.get("hits", 0)))
            return out
        if root.find(".//file[@name]") is not None:
            for file in root.iter("file"):
                path = resolve(file.get("name", ""), known)
                for line in file.iter("line"):
                    if line.get("type") == "stmt":
                        _add(out, path, int(line.get("num", 0)), int(line.get("count", 0)))
            return out
    elif any(line.startswith("SF:") for line in text.splitlines()):
        path = None
        for line in text.splitlines():
            if line.startswith("SF:"):
                path = resolve(line[3:].strip(), known)
            elif line.startswith("DA:"):
                number, hits = line[3:].split(",")[:2]
                _add(out, path, int(number), int(hits))
            elif line == "end_of_record":
                path = None
        return out
    raise ValueError(f"coverage: {report} is not a Cobertura, Clover or LCOV report")
