"""radon: the maintainability index of each Python file (0–100, higher is easier to maintain). `pip install radon`."""

from __future__ import annotations

from ..metrics import Measures


class Radon:
    name = "radon"
    measures = "maintainability index per Python file"

    def version(self) -> str | None:
        try:
            import radon
        except ImportError:
            return None
        return getattr(radon, "__version__", "") or "installed"

    def measure(self, files: dict[str, str], focus: set[str], clones: bool) -> Measures:
        from radon.metrics import mi_visit

        out = {}
        for path in sorted(focus & files.keys()):
            if path.endswith(".py"):
                try:
                    out[path] = {"mi": round(mi_visit(files[path], multi=True), 1)}
                except (SyntaxError, ValueError):
                    pass
        return Measures(files=out)


PROVIDER = Radon()
