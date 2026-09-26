"""Metrics as branch deltas: pair each touched function across the revisions, attach coverage, roll up by module."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import metrics as mt  # noqa: E402


def f(name, start, end, ccn, path="a.py", cls=None):
    return mt.Func(path, name, cls, start, end, {"ccn": ccn})


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.base = [f("kept", 1, 5, 2), f("changed", 10, 20, 3), f("gone", 30, 35, 4), f("run", 40, 41, 1, cls="A"), f("run", 42, 43, 1, cls="A")]
        self.head = [f("kept", 1, 5, 2), f("changed", 10, 22, 6), f("fresh", 30, 33, 1), f("run", 40, 41, 1, cls="A"), f("run", 42, 44, 2, cls="A")]
        self.changed = {"a.py": ({12, 30, 31, 43}, {12, 13, 14, 30, 31, 32, 33, 43, 44})}

    def test_only_touched_functions_paired_by_class_name_and_ordinal(self):
        got = [(r.cls, r.name, r.value("base", "ccn"), r.value("head", "ccn")) for r in mt.rows(self.base, self.head, self.changed)]
        self.assertEqual(got, [(None, "changed", 3, 6), (None, "fresh", None, 1), (None, "gone", 4, None), ("A", "run", 1, 2)])

    def test_delta_counts_a_missing_side_as_zero(self):
        by = {r.name: r for r in mt.rows(self.base, self.head, self.changed)}
        self.assertEqual((by["changed"].delta("ccn"), by["fresh"].delta("ccn"), by["gone"].delta("ccn")), (3, 1, -4))

    def test_coverage_is_the_share_of_executable_head_lines_hit(self):
        cov = {"a.py": {10: 1, 11: 0, 12: 3, 13: 0, 50: 1}}
        row = next(r for r in mt.rows(self.base, self.head, self.changed, cov) if r.name == "changed")
        self.assertEqual((row.covered, row.executable, row.coverage), (2, 4, 0.5))
        gone = next(r for r in mt.rows(self.base, self.head, self.changed, cov) if r.name == "gone")
        self.assertIsNone(gone.coverage)


class ClonesAndRollupTest(unittest.TestCase):
    def test_a_clone_counts_when_one_occurrence_is_on_a_changed_head_line(self):
        new = mt.Clone((("a.py", 10, 20), ("b.py", 1, 11)))
        old = mt.Clone((("b.py", 30, 40), ("c.py", 1, 11)))
        self.assertEqual(mt.touching([new, old], {"a.py": (set(), {15})}), [new])

    def test_rollup_by_module_with_diff_coverage(self):
        rows = mt.rows([f("x", 1, 3, 2)], [f("x", 1, 4, 5), f("y", 1, 2, 9, path="b.py")], {"a.py": (set(), {4}), "b.py": (set(), {1, 2})})
        clone = mt.Clone((("a.py", 1, 4), ("b.py", 1, 2)))
        module_of = {"a.py": ("m",), "b.py": ("n",)}.get
        cov = {"a.py": {4: 1}, "b.py": {1: 0, 2: 1}}
        got = mt.rollup(rows, [clone], module_of, {"a.py": (set(), {4}), "b.py": (set(), {1, 2, 3})}, cov)
        self.assertEqual((got[("m",)].functions, got[("m",)].ccn_delta, got[("m",)].ccn_max, got[("m",)].clones), (1, 3, 5, 1))
        self.assertEqual((got[("n",)].covered, got[("n",)].executable, got[("n",)].coverage), (1, 2, 0.5))
        self.assertEqual(got[("m",)].coverage, 1.0)

    def test_innermost_class(self):
        classes = [("Outer", 1, 20), ("Outer.Inner", 5, 10)]
        self.assertEqual([mt.innermost(classes, n) for n in (3, 7, 25)], ["Outer", "Outer.Inner", None])


if __name__ == "__main__":
    unittest.main()
