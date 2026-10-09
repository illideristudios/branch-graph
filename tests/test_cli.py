"""End to end: `branch-graph` on a throwaway git repo, no checkout of either revision."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from html import escape
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

    def panel(self, page, module):
        m = re.search(rf'<details id="(n-\d+)"><summary><span class="mono">{re.escape(module)}</span>.*?</details>', page, re.S)
        self.assertIsNotNone(m, module)
        return m.group(1), m.group(0)

    def test_new_edge_links_to_the_line_that_created_it(self):
        self.run_cli()
        page = self.out.read_text()
        anchor = re.search(r'href="#([\w-]+)"[^>]*>c\.py:2<', page).group(1)
        self.assertRegex(page, rf'<span[^>]*id="{anchor}"[^>]*>.*import a</span>')

    def test_diff_is_split_per_file_with_line_numbers(self):
        self.run_cli()
        _, b = self.panel(self.out.read_text(), "b")
        self.assertIn("b.py", b)
        self.assertRegex(b, r'<span class="l add"[^>]*><i></i><i>2</i>\+Y = ')
        self.assertRegex(b, r'<span class="l del"[^>]*><i>1</i><i></i>-X = 1')

    def test_panel_lists_connections_both_ways(self):
        self.run_cli()
        page = self.out.read_text()
        a_id, a = self.panel(page, "a")
        b_id, _ = self.panel(page, "b")
        c_id, c = self.panel(page, "c")
        self.assertIn(f'href="#{a_id}"', c)
        self.assertIn(f'href="#{b_id}"', c)
        self.assertIn(f'href="#{c_id}"', a)
        self.assertIn("Imported by", a)

    def test_every_drawn_edge_has_a_target_on_the_page(self):
        self.run_cli()
        page = self.out.read_text()
        mmd = self.out.with_suffix(".mmd").read_text()
        data = json.loads(re.search(r'<script type="application/json" id="bg-data">(.*?)</script>', page, re.S).group(1))
        self.assertEqual(len(data["links"]), len(re.findall(r" (?:-->|==>|-\.->) ", mmd)))
        for link in data["links"]:
            self.assertIn(f'id="{link["href"]}"', page)
            self.assertIn(" -> ", link["title"])

    def test_colors_override_the_page_and_the_diagram_follows(self):
        colors = Path(self.tmp.name, "colors.json")
        colors.write_text('{"light": {"add": "#00aa55"}, "dark": {"bg": "#000000"}}')
        self.run_cli("--colors", str(colors))
        page = self.out.read_text()
        self.assertIn("--add: #00aa55;", page)
        self.assertIn("--bg: #000000;", page)
        self.assertIn(".node.added rect {{ fill: var(--add-bg); stroke: var(--add); }}".replace("{{", "{").replace("}}", "}"), page)
        self.assertNotRegex(self.out.with_suffix(".mmd").read_text(), r"#[0-9a-f]{3,6}\b|var\(")

    def test_bad_colors_file_is_a_usage_error(self):
        colors = Path(self.tmp.name, "colors.json")
        colors.write_text('{"light": {"grene": "#0f0"}}')
        argv = [sys.executable, str(BIN), "--repo", str(self.repo), "--base", "base", "--root", ".", "--out", str(self.out), "--colors", str(colors)]
        run = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("unknown token 'grene'", run.stderr)

    def test_coverage_report_gives_diff_coverage_per_module(self):
        lcov = Path(self.tmp.name, "lcov.info")
        lcov.write_text(f"SF:{self.repo}/b.py\nDA:1,1\nDA:2,0\nend_of_record\nSF:c.py\nDA:1,1\nDA:2,1\nDA:3,1\nend_of_record\n")
        self.run_cli("--coverage", str(lcov))
        page = self.out.read_text()
        metrics = re.search(r'<section id="metrics">.*?</section>', page, re.S).group(0)
        self.assertRegex(metrics, r'>b</a>.*?50%')
        self.assertRegex(metrics, r'>c</a>.*?100%')
        self.assertIn("lcov.info", metrics)

    def test_a_bad_coverage_report_is_a_usage_error(self):
        bad = Path(self.tmp.name, "cov.txt")
        bad.write_text("nothing here\n")
        argv = [sys.executable, str(BIN), "--repo", str(self.repo), "--base", "base", "--root", ".", "--out", str(self.out), "--coverage", str(bad)]
        run = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn("not a Cobertura, Clover or LCOV", run.stderr)

    @unittest.skipUnless(importlib.util.find_spec("lizard"), "lizard not installed")
    def test_touched_functions_with_complexity_before_and_after(self):
        commit(self.repo, {"b.py": "X = 2\nY = '<x>'\n\ndef pick(a):\n    if a:\n        return 1\n    return 2\n"}, "more")
        self.run_cli()
        _, b = self.panel(self.out.read_text(), "b")
        self.assertRegex(b, r'<td[^>]*>.*pick.*</td><td[^>]*>— → 2</td>')

    def test_without_a_tool_the_section_says_what_to_install(self):
        hidden = Path(self.tmp.name, "hidden")
        hidden.mkdir()
        for name in ("lizard", "radon"):
            (hidden / f"{name}.py").write_text('raise ImportError("hidden for this test")\n')
        env = {**os.environ, "PYTHONPATH": str(hidden) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        argv = [sys.executable, str(BIN), "--repo", str(self.repo), "--base", "base", "--root", ".", "--out", str(self.out)]
        subprocess.run(argv, capture_output=True, text=True, check=True, env=env)
        self.assertIn("pip install lizard", self.out.read_text())

    def test_rules_and_notes(self):
        rules = Path(self.tmp.name, "ARCH.md")
        rules.write_text("```import-rules\nc -> b\n```\n")
        notes = Path(self.tmp.name, "notes.json")
        notes.write_text('{"c -> a": "c reads a\'s settings"}')
        lines = self.run_cli("--rules", str(rules), "--notes", str(notes)).splitlines()
        self.assertEqual(lines[0], "nodes +1 −0 ~1 edges +2 −0 drift=1")
        self.assertIn("c -> a  c.py:2  drift", lines)
        page = self.out.read_text()
        self.assertIn("c reads a&#x27;s settings", page)
        self.assertRegex(page, r"#graph svg #L_n\d+_n\d+_\d+ \{ stroke: var\(--drift\) !important; \}")


class ExcludeAndViewsCliTest(unittest.TestCase):
    """Test modules fan into the branch; `--exclude` drops them and `--max-nodes` splits the rest into page-K.mmd views."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name, "repo")
        (self.repo / "tests").mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "main")
        commit(self.repo, {"a.py": "import b\n", "b.py": "X = 1\n", "tests/test_a.py": "import a\n", "tests/test_b.py": "import b\n"}, "base")
        git(self.repo, "tag", "base")
        commit(self.repo, {"c.py": "import a\nimport b\n", "b.py": "X = 2\n", "tests/test_c.py": "import c\n",
                           "x.py": "import y\n", "y.py": "Y = 1\n"}, "head")
        self.out = Path(self.tmp.name, "page.html")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        argv = [sys.executable, str(BIN), "--repo", str(self.repo), "--base", "base", "--root", ".", "--out", str(self.out), *extra]
        return subprocess.run(argv, capture_output=True, text=True, check=True).stdout.splitlines()

    def views(self):
        return sorted(self.out.parent.glob("page-*.mmd"), key=lambda p: int(p.stem.split("-")[1]))

    def test_without_the_flags_output_is_unchanged(self):
        lines = self.run_cli()
        self.assertEqual(lines[0], "nodes +4 −0 ~1 edges +4 −0 drift=0")
        self.assertIn("tests.test_c -> c  tests/test_c.py:1  no rules", lines)
        self.assertTrue(self.out.with_suffix(".mmd").exists())
        self.assertEqual(self.views(), [])

    def test_exclude_is_repeatable_and_counted(self):
        lines = self.run_cli("--exclude", "tests.*", "--exclude", "y")
        self.assertEqual(lines[0], "nodes +2 −0 ~1 edges +2 −0 drift=0 excluded=4")
        self.assertEqual(sorted(lines[1:]), ["c -> a  c.py:1  no rules", "c -> b  c.py:2  no rules"])
        page, mmd = self.out.read_text(), self.out.with_suffix(".mmd").read_text()
        self.assertNotIn("tests.", mmd)
        self.assertNotIn("test_c", page)
        self.assertRegex(page, r"\b4 (?:modules? )?excluded\b")

    def test_views_replace_page_mmd(self):
        lines = self.run_cli("--exclude", "tests.*", "--max-nodes", "5")
        self.assertEqual(lines[0], "nodes +3 −0 ~1 edges +3 −0 drift=0 excluded=3 views=2")
        self.assertEqual(sorted(lines[1:]), ["c -> a  c.py:1  no rules", "c -> b  c.py:2  no rules", "x -> y  x.py:1  no rules"])
        self.assertFalse(self.out.with_suffix(".mmd").exists())
        views = self.views()
        self.assertEqual([p.name for p in views], ["page-1.mmd", "page-2.mmd"])
        page = self.out.read_text()
        self.assertRegex(page, r"\b3 (?:modules? )?excluded\b")
        at = -1
        for view in views:
            mmd = view.read_text()
            first = mmd.splitlines()[0]
            self.assertRegex(first, r"^%% view: \S+( and \d+ more)?$")
            self.assertNotIn("tests.", mmd)
            clicks = re.findall(r'^\s+click \S+ href "#([\w-]+)"', mmd, re.M)
            self.assertLessEqual(len(clicks), 5)
            for anchor in clicks:
                self.assertIn(f'id="{anchor}"', page)
            title = first.removeprefix("%% view: ")
            self.assertGreater(page.find(escape(title), at + 1), at, f"{title} out of order")
            at = page.find(escape(title), at + 1)


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
