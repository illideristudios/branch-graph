"""The core: graphs, collapse, diff, rules. Pure, so no git and no language."""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE.parent / "lib"
sys.path.insert(0, str(LIB))

from branch_graph import domain as d  # noqa: E402


def graph(edges, files):
    """files: {path: module tuple}; edges: [(src, dst, path, line)]."""
    g = d.Graph(files=dict(files))
    for src, dst, path, line in edges:
        g.add(d.Edge(src, dst, path, line))
    return g


A, B, C = ("app", "a", "x"), ("app", "b"), ("app", "c", "y")


class CollapseTest(unittest.TestCase):
    def test_depth_two_truncates_and_keeps_flat_modules(self):
        g = d.collapse(graph([(A, B, "app/a/x.py", 3)], {"app/a/x.py": A, "app/b.py": B}), 2)
        self.assertEqual(g.nodes, {("app", "a"), ("app", "b")})
        self.assertEqual([(e.src, e.dst, e.file, e.line) for e in g.edges.values()], [(("app", "a"), ("app", "b"), "app/a/x.py", 3)])

    def test_depth_one_drops_self_edges(self):
        g = d.collapse(graph([(A, B, "app/a/x.py", 3)], {"app/a/x.py": A, "app/b.py": B}), 1)
        self.assertEqual(g.nodes, {("app",)})
        self.assertEqual(g.edges, {})


class DiffTest(unittest.TestCase):
    def setUp(self):
        self.base = graph([(A, B, "app/a/x.py", 1), (B, C, "app/b.py", 4)], {"app/a/x.py": A, "app/b.py": B, "app/c/y.py": C})
        head_files = {"app/a/x.py": A, "app/b.py": B, "app/n.py": ("app", "n")}
        self.head = graph([(A, B, "app/a/x.py", 1), (("app", "n"), A, "app/n.py", 2)], head_files)
        self.bd = d.diff(self.base, self.head, {"app/b.py": (5, 2), "app/n.py": (9, 0), "app/c/y.py": (0, 7)})

    def test_nodes(self):
        self.assertEqual(self.bd.added, {("app", "n")})
        self.assertEqual(self.bd.removed, {C})
        self.assertEqual(self.bd.changed, {B: (5, 2)})

    def test_edges_carry_their_file_line(self):
        self.assertEqual([(e.src, e.dst, e.file, e.line) for e in self.bd.edges_added], [(("app", "n"), A, "app/n.py", 2)])
        self.assertEqual([(e.src, e.dst, e.file, e.line) for e in self.bd.edges_removed], [(B, C, "app/b.py", 4)])


class RulesTest(unittest.TestCase):
    edge_ca = d.Edge(("c",), ("a",), "c.py", 1)
    edge_cb = d.Edge(("c",), ("b",), "c.py", 2)

    def test_edge_no_rule_allows_is_drift(self):
        rules = d.parse_rules("# Arch\n\n```import-rules\nc -> b\n```\n")
        self.assertEqual(d.verdict(self.edge_cb, rules), "allowed")
        self.assertEqual(d.verdict(self.edge_ca, rules), "drift")

    def test_globs(self):
        rules = d.parse_rules("```import-rules\napp.web* -> app.*\n```")
        self.assertEqual(d.verdict(d.Edge(("app", "web"), ("app", "rag"), "f", 1), rules), "allowed")

    def test_no_block_is_no_rules_never_invented(self):
        self.assertIsNone(d.parse_rules("# Arch\n\nno block here\n"))
        self.assertEqual(d.verdict(self.edge_ca, None), "no rules")


class DependencyRuleTest(unittest.TestCase):
    """Clean Architecture: the core imports no adapter, no git, no language."""

    def test_core_imports_no_adapter(self):
        banned = {"subprocess", "branch_graph.git_source", "branch_graph.render", "branch_graph.languages"}
        for name in ("domain.py", "use_case.py", "ports.py"):
            tree = ast.parse((LIB / "branch_graph" / name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    pkg = ".".join(filter(None, ["branch_graph" if node.level else "", node.module]))
                    mods = [pkg] + [f"{pkg}.{a.name}" for a in node.names]
                else:
                    continue
                for mod in mods:
                    self.assertFalse(any(mod == b or mod.startswith(b + ".") for b in banned), f"{name} imports {mod}")


if __name__ == "__main__":
    unittest.main()
