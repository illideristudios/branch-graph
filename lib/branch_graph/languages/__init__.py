"""The language registry: every file in this directory not starting with `_` is a language exposing `MODULE`."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load(directory: Path = Path(__file__).parent) -> list:
    modules = []
    for file in sorted(directory.glob("[!_]*.py")):
        spec = importlib.util.spec_from_file_location(f"{__name__}.{file.stem}", file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module.MODULE)
    return modules


def selector(modules: list):
    """path -> the first language that claims it, or None."""
    return lambda path: next((m for m in modules if m.claims(path)), None)
