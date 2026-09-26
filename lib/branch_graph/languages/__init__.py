"""The language registry: every file in this directory not starting with `_` is a language exposing `MODULE`."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def load(directory: Path = Path(__file__).parent, attr: str = "MODULE", package: str = __name__) -> list:
    """`attr` of every file in `directory` not starting with `_`, in name order. The metrics providers load this way too."""
    modules = []
    for file in sorted(directory.glob("[!_]*.py")):
        spec = importlib.util.spec_from_file_location(f"{package}.{file.stem}", file, submodule_search_locations=None)
        module = importlib.util.module_from_spec(spec)
        module.__package__ = package
        spec.loader.exec_module(module)
        modules.append(getattr(module, attr))
    return modules


def selector(modules: list):
    """path -> the first language that claims it, or None."""
    return lambda path: next((m for m in modules if m.claims(path)), None)
