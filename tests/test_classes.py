"""Class ranges, so a function lizard names bare can be attributed to its class."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph.languages.php import MODULE as php  # noqa: E402
from branch_graph.languages.python import MODULE as py  # noqa: E402
from branch_graph.languages.swift import MODULE as swift  # noqa: E402


class ClassesTest(unittest.TestCase):
    def test_python_nested_classes_are_qualified(self):
        src = "class A:\n    def f(self):\n        pass\n\n    class B:\n        x = 1\n\ndef g():\n    pass\n"
        self.assertEqual(py.classes(src), [("A", 1, 6), ("A.B", 5, 6)])

    def test_swift_types_and_extensions_ignoring_braces_in_strings_and_comments(self):
        src = 'struct User {\n  let s = "}"\n  // }\n  class func make() {}\n}\nextension User {\n  func z() {}\n}\n'
        self.assertEqual(swift.classes(src), [("User", 1, 5), ("User", 6, 8)])

    def test_php_classes_not_class_constants(self):
        src = "<?php\nclass Db {\n  function q() { return Foo::class; }\n  /* { */\n}\ninterface I {}\n"
        self.assertEqual(php.classes(src), [("Db", 2, 5), ("I", 6, 6)])


if __name__ == "__main__":
    unittest.main()
