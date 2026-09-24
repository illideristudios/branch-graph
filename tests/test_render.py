"""The diagram draws what the branch touched and one hop around it, and nothing between two untouched modules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import domain as d, render  # noqa: E402


class DrawnTest(unittest.TestCase):
    def test_context_to_context_edges_are_not_drawn(self):
        files = {f"{m}.py": (m,) for m in "tcxyz"}
        base = d.Graph(files=dict(files))
        head = d.Graph(files=dict(files))
        for g in (base, head):
            g.add(d.Edge(("x",), ("t",), "x.py", 1))
            g.add(d.Edge(("z",), ("t",), "z.py", 1))
            g.add(d.Edge(("x",), ("z",), "x.py", 2))
        head.add(d.Edge(("t",), ("c",), "t.py", 1))
        bd = d.diff(base, head, {"t.py": (1, 0)})
        shown, rest = render.drawn(bd)
        self.assertEqual(shown, [("c",), ("t",), ("x",), ("z",)])
        self.assertEqual(rest, 1)
        mmd = render.mermaid(bd, {}, shown, rest)
        self.assertEqual(mmd.count("-->") + mmd.count("==>"), 3)


if __name__ == "__main__":
    unittest.main()
