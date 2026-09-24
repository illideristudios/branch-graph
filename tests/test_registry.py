"""The language registry: a new language is a new file, and no core file changes."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import languages  # noqa: E402

FAKE = '''
class Fake:
    name = "fake"
    def claims(self, path): return path.endswith(".txt")
    def module_of(self, path, root): return (path,)
    def imports(self, path, module, source, known): return []

MODULE = Fake()
'''


class RegistryTest(unittest.TestCase):
    def test_python_ships(self):
        select = languages.selector(languages.load())
        self.assertEqual(select("app/x.py").name, "python")
        self.assertIsNone(select("notes.txt"))

    def test_dropped_in_module_is_picked_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "fake.py").write_text(FAKE)
            Path(tmp, "_private.py").write_text("raise SystemExit('not a language')")
            select = languages.selector(languages.load(Path(tmp)))
            self.assertEqual(select("notes.txt").name, "fake")
            self.assertIsNone(select("app/x.py"))


if __name__ == "__main__":
    unittest.main()
