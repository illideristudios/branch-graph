"""End to end: `branch-graph` on a throwaway git repo, no checkout of either revision."""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = HERE.parent / "bin" / "branch-graph"


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def commit(repo, files, msg):
    for name, text in files.items():
        Path(repo, name).write_text(text)
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name, "repo")
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        commit(self.repo, {"a.py": "import b\n", "b.py": "X = 1\n"}, "base")
        git(self.repo, "tag", "base")
        commit(self.repo, {"c.py": "import os\nimport a\nimport b\n", "b.py": "X = 2\nY = '<x>'\n"}, "head")
        self.out = Path(self.tmp.name, "page.html")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        argv = [sys.executable, str(BIN), "--repo", str(self.repo), "--base", "base", "--root", ".", "--out", str(self.out), *extra]
        return subprocess.run(argv, capture_output=True, text=True, check=True).stdout

    def test_summary_and_new_edges(self):
        lines = self.run_cli().splitlines()
        self.assertEqual(lines[0], "nodes +1 −0 ~1 edges +2 −0 drift=0")
        self.assertEqual(sorted(lines[1:]), ["c -> a  c.py:2  no rules", "c -> b  c.py:3  no rules"])

    def test_page_links_every_node_to_its_hunks(self):
        self.run_cli()
        page = self.out.read_text()
        mmd = self.out.with_suffix(".mmd").read_text()
        hrefs = set(re.findall(r'click \S+ href "#(n-\d+)"', mmd))
        self.assertEqual(len(hrefs), 3)
        for anchor in hrefs:
            self.assertIn(f'<details id="{anchor}"', page)
        self.assertIn("Y = &#x27;&lt;x&gt;&#x27;", page)
        self.assertIn("securityLevel", page)

    def test_rules_and_notes(self):
        rules = Path(self.tmp.name, "ARCH.md")
        rules.write_text("```import-rules\nc -> b\n```\n")
        notes = Path(self.tmp.name, "notes.json")
        notes.write_text('{"c -> a": "c reads a\'s settings"}')
        lines = self.run_cli("--rules", str(rules), "--notes", str(notes)).splitlines()
        self.assertEqual(lines[0], "nodes +1 −0 ~1 edges +2 −0 drift=1")
        self.assertIn("c -> a  c.py:2  drift", lines)
        self.assertIn("c reads a&#x27;s settings", self.out.read_text())


class PhpCliTest(unittest.TestCase):
    """Namespaced files are named by namespace, legacy ones by path, and a `use` links them; a .py file rides along."""

    def test_legacy_file_using_namespaced_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp, "repo")
            (repo / "src").mkdir(parents=True)
            (repo / "legacy").mkdir()
            git(repo, "init", "-q", "-b", "main")
            commit(repo, {
                "src/Db.php": "<?php\nnamespace App;\n\nclass Db {}\n",
                "src/Web.php": "<?php\nnamespace App;\nuse App\\Db;\n\nclass Web {}\n",
                "tool.py": "import os\n",
            }, "base")
            git(repo, "tag", "base")
            commit(repo, {
                "src/Db.php": "<?php\nnamespace App;\n\nclass Db { const X = 1; }\n",
                "legacy/page.php": "<?php\nuse App\\Web;\nuse App\\Db;\nuse Symfony\\Yaml\\Yaml;\n",
            }, "head")
            out = Path(tmp, "page.html")
            argv = [sys.executable, str(BIN), "--repo", str(repo), "--base", "base", "--root", ".", "--out", str(out)]
            lines = subprocess.run(argv, capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(lines[0], "nodes +1 −0 ~1 edges +2 −0 drift=0")
            self.assertEqual(sorted(lines[1:]), ["legacy.page -> App.Db  legacy/page.php:3  no rules", "legacy.page -> App.Web  legacy/page.php:2  no rules"])


if __name__ == "__main__":
    unittest.main()
