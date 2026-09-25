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


if __name__ == "__main__":
    unittest.main()
