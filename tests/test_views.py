"""`--exclude` drops modules before anything is drawn; `--max-nodes` splits the drawing into views of at most N nodes."""

from __future__ import annotations

import fnmatch
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import domain as d, render  # noqa: E402


def mod(s: str) -> d.ModuleId:
    return tuple(s.split("."))


def path(s: str) -> str:
    return s.replace(".", "/") + ".py"


def branch(same=(), new=(), changed=(), added=()) -> d.BranchDiff:
    """Dotted names. same: edges in both revisions; new: edges only in head; changed: modules with lines changed;
    added: modules only in head. Every other module named by an edge exists in both."""
    names = {n for e in (*same, *new) for n in e} | set(changed) | set(added)
    base = d.Graph(files={path(n): mod(n) for n in names - set(added)})
    head = d.Graph(files={path(n): mod(n) for n in names})
    for g, es in ((base, same), (head, (*same, *new))):
        for i, (src, dst) in enumerate(es):
            g.add(d.Edge(mod(src), mod(dst), path(src), i + 1))
    return d.diff(base, head, {path(n): (1, 0) for n in changed})


CLICK = re.compile(r"^\s+click (\S+) href", re.M)
NODE = re.compile(r'^\s+(\S+)\["(.*?)"\]', re.M)


def module_labels(mmd: str) -> list[str]:
    """Labels of the module nodes: the clickable ones, so a `… N more` note is not a node."""
    clickable = set(CLICK.findall(mmd))
    return [label for nid, label in NODE.findall(mmd) if nid in clickable]


class ViewInvariantsTest(unittest.TestCase):
    """One synthetic branch with a chain, a star, a hub with many context neighbours, excluded tests, and two small
    islands; the rules hold at every N."""

    def setUp(self):
        chain = [f"c{i:02}" for i in range(20)]
        stars = [f"s{i:02}" for i in range(10)]
        ctx = [f"h{i:02}" for i in range(30)]
        tests = [f"tests.t{i:02}" for i in range(30)]
        same = list(zip(chain, chain[1:])) + [(s, "star") for s in stars] + [(h, "hub") for h in ctx] + [(t, "hub") for t in tests]
        same += [(t, "c05") for t in tests[:10]] + [("hub", h) for h in ctx[:5]] + [("x9", "c10"), ("x9", "star")]
        new = [("tests.new", "hub"), ("p1", "p2"), ("q1", "q2"), ("p1", "x9")]
        full = branch(same=same, new=new, changed=[*chain, *stars, "star", "hub", "tests.t03"], added=["tests.new"])
        self.bd, self.excluded = d.exclude(full, ["tests.*"])

    def views(self, n):
        views = render.views(self.bd, n)
        self.assertTrue(views)
        return views

    def test_exclusion_counts_every_excluded_module(self):
        self.assertEqual(self.excluded, 31)

    def test_excluded_modules_appear_nowhere(self):
        excluded = lambda m: fnmatch.fnmatchcase(d.name(m), "tests.*")  # noqa: E731
        everything = self.bd.base.nodes | self.bd.head.nodes | render.touched(self.bd)
        self.assertFalse([m for m in everything if excluded(m)])
        self.assertFalse([k for k in {**self.bd.base.edges, **self.bd.head.edges} if excluded(k[0]) or excluded(k[1])])
        for n in (3, 5, 8, 12):
            for v in self.views(n):
                self.assertFalse([m for m in v.shown if excluded(m)], n)
                self.assertNotIn("tests.", render.view_mermaid(self.bd, {}, v))

    def test_no_view_exceeds_n(self):
        for n in (3, 4, 5, 8, 12):
            for v in self.views(n):
                self.assertLessEqual(len(v.shown), n, v.title)
                self.assertEqual(len(set(v.shown)), len(v.shown), v.title)
                self.assertLessEqual(len(module_labels(render.view_mermaid(self.bd, {}, v))), n, v.title)

    def test_every_touched_module_is_touched_in_exactly_one_view(self):
        for n in (3, 5, 8, 12):
            views = self.views(n)
            count = Counter(m for v in views for m in v.touched)
            self.assertEqual(set(count), render.touched(self.bd), n)
            self.assertEqual(max(count.values()), 1, n)
            for v in views:
                self.assertLessEqual(set(v.touched), set(v.shown), v.title)

    def test_an_edge_between_touched_modules_is_drawn_in_some_view(self):
        # From N=5: at N=3 a module with three touched neighbours in other views makes this a cover problem.
        hot = render.touched(self.bd)
        for n in (5, 8, 12):
            views = self.views(n)
            drawn = {(e.src, e.dst) for v in views for e, _ in render.links(self.bd, v.shown)}
            for e, _ in render.edges(self.bd):
                if e.src in hot and e.dst in hot:
                    self.assertIn((e.src, e.dst), drawn, f"N={n}: {e.key}")

    def test_titles_name_the_first_touched_module_and_how_many_more(self):
        for n in (3, 8):
            for v in self.views(n):
                more = len(v.touched) - 1
                self.assertEqual(v.title, d.name(v.touched[0]) + (f" and {more} more" if more else ""))
                self.assertEqual(render.view_mermaid(self.bd, {}, v).splitlines()[0], f"%% view: {v.title}")

    def test_a_module_touched_in_another_view_is_marked_with_that_view(self):
        hot = render.touched(self.bd)
        for n in (3, 5, 8):
            views = self.views(n)
            home = {m: k for k, v in enumerate(views, 1) for m in v.touched}
            for k, v in enumerate(views, 1):
                visitors = {m for m in v.shown if m in hot and m not in v.touched}
                self.assertEqual(v.elsewhere, {m: home[m] for m in visitors}, v.title)
                labels = module_labels(render.view_mermaid(self.bd, {}, v))
                for m, home_view in v.elsewhere.items():
                    mine = [label for label in labels if re.match(re.escape(d.name(m)) + r"(?![\w.])", label)]
                    self.assertEqual(len(mine), 1, f"{v.title}: {d.name(m)}")
                    self.assertIn(f"view {home_view}", mine[0], v.title)


class ViewShapesTest(unittest.TestCase):
    def test_thirty_excluded_test_modules_leave_a_small_graph(self):
        tests = [f"tests.t{i:02}" for i in range(30)]
        full = branch(same=[(t, "core") for t in tests] + [(a, "core") for a in ("a1", "a2", "a3")], changed=["core"])
        bd, excluded = d.exclude(full, ["tests.*"])
        self.assertEqual(excluded, 30)
        self.assertEqual(render.drawn(bd), ([("a1",), ("a2",), ("a3",), ("core",)], 0))
        [view] = render.views(bd, 12)
        self.assertEqual(sorted(view.shown), [("a1",), ("a2",), ("a3",), ("core",)])
        self.assertEqual((view.touched, view.rest, view.title), ([("core",)], 0, "core"))

    def test_a_lone_module_keeps_its_most_connected_neighbours(self):
        ctx = [f"n{i:02}" for i in range(30)]
        # n25..n29 import core and are imported by it: two ties each, so they must win the eleven context places.
        bd = branch(same=[(n, "core") for n in ctx] + [("core", n) for n in ctx[25:]], changed=["core"])
        [view] = render.views(bd, 12)
        self.assertEqual(view.touched, [("core",)])
        self.assertEqual(len(view.shown), 12)
        self.assertLessEqual({mod(n) for n in ctx[25:]}, set(view.shown))
        self.assertEqual(view.rest, 19)
        self.assertIn("19 more", render.view_mermaid(bd, {}, view))

    def test_two_disconnected_clusters_are_two_views(self):
        bd = branch(same=[("u1", "p1"), ("u2", "q2")], new=[("p1", "p2"), ("q1", "q2")])
        views = render.views(bd, 10)
        self.assertEqual(len(views), 2)
        self.assertEqual({frozenset(v.touched) for v in views}, {frozenset({("p1",), ("p2",)}), frozenset({("q1",), ("q2",)})})

    def test_a_connected_cluster_bigger_than_n_is_split(self):
        chain = [f"c{i:02}" for i in range(20)]
        bd = branch(same=list(zip(chain, chain[1:])), changed=chain)
        views = render.views(bd, 8)
        self.assertGreaterEqual(len(views), 3)
        self.assertTrue(all(len(v.shown) <= 8 for v in views))
        self.assertEqual(sorted(m for v in views for m in v.touched), [mod(c) for c in chain])

    def test_a_connected_cluster_that_fits_stays_together(self):
        bd = branch(same=[("a", "b"), ("b", "c"), ("c", "d")], changed=["a", "b", "c", "d"])
        [view] = render.views(bd, 8)
        self.assertEqual(sorted(view.touched), [("a",), ("b",), ("c",), ("d",)])
        self.assertEqual(view.title, f"{d.name(view.touched[0])} and 3 more")

    def test_fewer_than_three_nodes_is_refused(self):
        bd = branch(same=[("a", "b")], changed=["a"])
        with self.assertRaises(ValueError):
            render.views(bd, 2)


class SummaryTest(unittest.TestCase):
    def setUp(self):
        self.bd = branch(new=[("a", "b")], changed=["b"])

    def test_without_the_flags_the_line_is_unchanged(self):
        self.assertEqual(render.summary(self.bd, {}), "nodes +0 −0 ~1 edges +1 −0 drift=0")

    def test_excluded_and_views_are_appended(self):
        self.assertEqual(render.summary(self.bd, {}, excluded=31), "nodes +0 −0 ~1 edges +1 −0 drift=0 excluded=31")
        self.assertEqual(render.summary(self.bd, {}, views=4), "nodes +0 −0 ~1 edges +1 −0 drift=0 views=4")
        self.assertEqual(render.summary(self.bd, {}, excluded=0, views=2), "nodes +0 −0 ~1 edges +1 −0 drift=0 excluded=0 views=2")


if __name__ == "__main__":
    unittest.main()
