"""Coverage reports (Cobertura, Clover, LCOV) read into {repo path: {line: hits}}, whatever path form the report used."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import coverage_report  # noqa: E402

KNOWN = ["src/app/web.py", "src/app/db.py", "tests/web.py", "lib/Db.php"]

COBERTURA = """<?xml version="1.0" ?>
<coverage version="7.6"><sources><source>/ci/checkout/src</source></sources>
<packages><package name="app"><classes>
<class name="web.py" filename="app/web.py"><lines><line number="1" hits="1"/><line number="2" hits="0"/></lines></class>
</classes></package></packages></coverage>"""

CLOVER = """<?xml version="1.0"?>
<coverage generated="1"><project><package name="x"><file name="/home/ci/repo/lib/Db.php">
<line num="3" type="stmt" count="2"/><line num="4" type="method" count="1"/><line num="5" type="stmt" count="0"/>
</file></package></project></coverage>"""

LCOV = "TN:\nSF:/abs/elsewhere/src/app/db.py\nDA:1,4\nDA:7,0\nend_of_record\nSF:gone.py\nDA:1,1\nend_of_record\n"


class ReadTest(unittest.TestCase):
    def read(self, text, name="report"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, name)
            path.write_text(text)
            return coverage_report.read(path, KNOWN)

    def test_cobertura(self):
        self.assertEqual(self.read(COBERTURA, "coverage.xml"), {"src/app/web.py": {1: 1, 2: 0}})

    def test_clover_statements_only(self):
        self.assertEqual(self.read(CLOVER, "clover.xml"), {"lib/Db.php": {3: 2, 5: 0}})

    def test_lcov_drops_files_the_repo_does_not_have(self):
        self.assertEqual(self.read(LCOV, "lcov.info"), {"src/app/db.py": {1: 4, 7: 0}})

    def test_an_ambiguous_basename_needs_more_of_the_path(self):
        self.assertEqual(coverage_report.resolve("web.py", KNOWN), None)
        self.assertEqual(coverage_report.resolve("app/web.py", KNOWN), "src/app/web.py")

    def test_unknown_format_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "not a Cobertura, Clover or LCOV"):
            self.read("hello\n")


if __name__ == "__main__":
    unittest.main()
