"""GitSource.read_all: many files at a revision in one `git cat-file --batch`, byte offsets and all."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
sys.path.insert(0, str(HERE))

from branch_graph.git_source import GitSource  # noqa: E402
from test_cli import commit, git  # noqa: E402


class ReadAllTest(unittest.TestCase):
    def test_reads_many_files_and_tolerates_a_missing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q", "-b", "main")
            commit(tmp, {"a.txt": "one\n", "b c.txt": "two\nlines\r\n", "empty.txt": "", "é.txt": "ünï\n"}, "x")
            got = GitSource(tmp).read_all("HEAD", ["a.txt", "b c.txt", "empty.txt", "é.txt", "gone.txt"])
            self.assertEqual(got, {"a.txt": "one\n", "b c.txt": "two\nlines\r\n", "empty.txt": "", "é.txt": "ünï\n", "gone.txt": ""})
            self.assertEqual(GitSource(tmp).read_all("HEAD", []), {})


class NonAsciiPathTest(unittest.TestCase):
    """git quotes a non-ASCII path unless asked not to; a quoted path is a file the graph silently loses."""

    def test_files_and_numstat_keep_the_real_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q", "-b", "main")
            commit(tmp, {"a.py": "x = 1\n"}, "base")
            commit(tmp, {"é.py": "import a\n", "b c.py": "y = 2\n"}, "head")
            source = GitSource(tmp)
            self.assertEqual(sorted(source.files("HEAD", ".")), ["a.py", "b c.py", "é.py"])
            self.assertEqual(source.numstat("HEAD~1", "HEAD", "."), {"b c.py": (1, 0), "é.py": (1, 0)})
            self.assertIn("diff --git a/é.py b/é.py", source.hunks("HEAD~1", "HEAD", ["é.py"]))


class ChangedLinesTest(unittest.TestCase):
    def test_base_and_head_line_numbers_per_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q", "-b", "main")
            commit(tmp, {"a.py": "1\n2\n3\n4\n5\n", "gone.py": "x\n"}, "base")
            Path(tmp, "gone.py").unlink()
            commit(tmp, {"a.py": "1\ntwo\n3\n5\n6\n7\n", "new.py": "n\n"}, "head")
            got = GitSource(tmp).changed_lines("HEAD~1", "HEAD", ".")
            self.assertEqual(got, {"a.py": ({2, 4}, {2, 5, 6}), "gone.py": ({1}, set()), "new.py": (set(), {1})})


if __name__ == "__main__":
    unittest.main()
