"""Metrics providers: optional libraries, each reporting only when it is installed."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import providers  # noqa: E402

HAS_LIZARD = importlib.util.find_spec("lizard") is not None
HAS_RADON = importlib.util.find_spec("radon") is not None
BLOCK = "".join(f"    total = total + values[{i}] * weights[{i}] - offsets[{i}]\n" for i in range(12))


def by_name(name):
    return next(p for p in providers.load(available_only=False) if p.name == name)


class RegistryTest(unittest.TestCase):
    def test_ships_lizard_and_radon_and_reports_availability(self):
        names = {p.name: bool(p.version()) for p in providers.load(available_only=False)}
        self.assertEqual(names, {"lizard": HAS_LIZARD, "radon": HAS_RADON})
        self.assertEqual({p.name for p in providers.load()}, {n for n, ok in names.items() if ok})


@unittest.skipUnless(HAS_LIZARD, "lizard not installed")
class LizardTest(unittest.TestCase):
    def test_functions_in_focus_with_complexity_and_php_class(self):
        files = {"a.py": "def f(x):\n    if x:\n        return 1\n    return 2\n", "b.php": "<?php\nclass Db {\n  function q($s) { return $s ? 1 : 0; }\n}\n"}
        got = by_name("lizard").measure(files, {"a.py", "b.php"}, clones=False)
        rows = sorted((fn.path, fn.cls, fn.name, fn.start, fn.end, fn.values["ccn"]) for fn in got.functions)
        self.assertEqual(rows, [("a.py", None, "f", 1, 4, 2), ("b.php", "Db", "q", 3, 3, 2)])

    def test_clones_across_files(self):
        files = {"a.py": f"def f(values, weights, offsets):\n    total = 0\n{BLOCK}    return total\n", "b.py": f"def g(values, weights, offsets):\n    total = 0\n{BLOCK}    return total\n"}
        got = by_name("lizard").measure(files, {"a.py"}, clones=True)
        self.assertEqual([fn.path for fn in got.functions], ["a.py"])
        self.assertTrue(any({p for p, _, _ in c.snippets} == {"a.py", "b.py"} for c in got.clones), got.clones)


@unittest.skipUnless(HAS_RADON, "radon not installed")
class RadonTest(unittest.TestCase):
    def test_maintainability_index_per_python_file(self):
        got = by_name("radon").measure({"a.py": "def f(x):\n    return x\n", "b.php": "<?php\n"}, {"a.py", "b.php"}, clones=False)
        self.assertEqual(list(got.files), ["a.py"])
        self.assertGreater(got.files["a.py"]["mi"], 50)


if __name__ == "__main__":
    unittest.main()
