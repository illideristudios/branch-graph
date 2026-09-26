"""lizard: cyclomatic complexity, lines and parameters per function, and token-based duplication (flog and flay for
the languages branch-graph reads). `pip install lizard`."""

from __future__ import annotations

from ..metrics import Clone, Func, Measures

MIN_DUPLICATE_TOKENS = 70  # lizard's own default for -Eduplicate


class Lizard:
    name = "lizard"
    measures = "complexity, lines and parameters per function; duplication"

    def version(self) -> str | None:
        try:
            import lizard
        except ImportError:
            return None
        return getattr(lizard, "version", "") or "installed"

    def measure(self, files: dict[str, str], focus: set[str], clones: bool) -> Measures:
        """Functions of the files in `focus`; with `clones`, duplicated blocks across all of `files`."""
        import lizard
        from lizard_ext.lizardduplicate import LizardExtension

        dup = LizardExtension() if clones else None
        analyzer = lizard.FileAnalyzer(lizard.get_extensions([dup] if dup else []))
        infos, funcs = [], []
        for path in sorted(files if clones else focus & files.keys()):
            info = analyzer.analyze_source_code(path, files[path])
            infos.append(info)
            if path in focus:
                for f in info.function_list:
                    cls, _, name = f.name.rpartition("::")
                    funcs.append(Func(path, name, cls or None, f.start_line, f.end_line,
                                      {"ccn": f.cyclomatic_complexity, "nloc": f.nloc, "params": f.parameter_count}))
        found = []
        if dup:
            list(dup.cross_file_process(infos))
            found = [Clone(tuple((s.file_name, s.start_line, s.end_line) for s in snippets))
                     for snippets in dup.get_duplicates(min_duplicate_tokens=MIN_DUPLICATE_TOKENS)]
        return Measures(funcs, {}, found)


PROVIDER = Lizard()
