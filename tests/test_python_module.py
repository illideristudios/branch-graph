"""The Python language module: ast imports resolved to the revision's own modules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph.languages.python import MODULE as py  # noqa: E402

KNOWN = {("a",), ("b",), ("pkg",), ("pkg", "x"), ("pkg", "sub"), ("pkg", "sub", "deep")}


def imports(path, source, root="."):
    return list(py.imports(path, py.module_of(path, root), source, KNOWN))


class ModuleOfTest(unittest.TestCase):
    def test_paths_under_root(self):
        self.assertEqual(py.module_of("agent/app/graph/x.py", "agent"), ("app", "graph", "x"))
        self.assertEqual(py.module_of("pkg/__init__.py", "."), ("pkg",))
        self.assertTrue(py.claims("a.py"))
        self.assertFalse(py.claims("a.txt"))


class ImportsTest(unittest.TestCase):
    def test_plain_import_with_its_line(self):
        self.assertEqual(imports("a.py", "import os\n\nimport b\n"), [(("b",), 3)])

    def test_third_party_dropped(self):
        self.assertEqual(imports("a.py", "import requests\nfrom requests import get\n"), [])

    def test_from_pkg_import_module(self):
        self.assertEqual(imports("a.py", "from pkg import x\n"), [(("pkg", "x"), 1)])

    def test_from_pkg_import_name_is_the_package(self):
        self.assertEqual(imports("a.py", "from pkg import some_function\n"), [(("pkg",), 1)])

    def test_dotted_import_takes_longest_known_prefix(self):
        self.assertEqual(imports("a.py", "import pkg.sub.deep.attr\n"), [(("pkg", "sub", "deep"), 1)])

    def test_relative_import_resolves(self):
        self.assertEqual(imports("pkg/sub/deep.py", "from . import x\nfrom .. import x\n"), [(("pkg", "sub"), 1), (("pkg", "x"), 2)])
        self.assertEqual(imports("pkg/sub/__init__.py", "from .deep import f\n"), [(("pkg", "sub", "deep"), 1)])

    def test_syntax_error_yields_nothing(self):
        self.assertEqual(imports("a.py", "def (:\n"), [])


if __name__ == "__main__":
    unittest.main()
