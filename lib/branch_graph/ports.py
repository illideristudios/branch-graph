"""What the core needs from the outside world. Adapters implement these; the core never imports an adapter."""

from __future__ import annotations

from typing import Iterable, Protocol

from .domain import ModuleId


class LanguageModule(Protocol):
    """One language. A new language is a new file in `languages/` exposing `MODULE`."""

    name: str

    def claims(self, path: str) -> bool: ...

    def module_of(self, path: str, root: str) -> ModuleId | None: ...

    def imports(self, path: str, module: ModuleId, source: str, known: set[ModuleId]) -> Iterable[tuple[ModuleId, int]]:
        """(imported module, line) for each import that names a module in `known`; anything else is external."""
        ...


class RevisionSource(Protocol):
    """Files at a revision, read without a checkout."""

    def files(self, rev: str, root: str) -> list[str]: ...

    def read(self, rev: str, path: str) -> str: ...

    def numstat(self, base: str, head: str, root: str) -> dict[str, tuple[int, int]]: ...

    def hunks(self, base: str, head: str, paths: list[str]) -> str: ...
