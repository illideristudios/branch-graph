"""Metrics providers: every file here not starting with `_` exposes `PROVIDER`, an optional library behind one call.

A provider imports its library inside `version` and `measure`, never at the top of its file, so a machine without the
library still loads the registry and simply gets no numbers from it.
"""

from __future__ import annotations

from pathlib import Path

from .. import languages


def load(available_only: bool = True) -> list:
    found = languages.load(Path(__file__).parent, "PROVIDER", __name__)
    return [p for p in found if p.version()] if available_only else found
