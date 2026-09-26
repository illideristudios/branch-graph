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


class BudgetTest(unittest.TestCase):
    """Context is added most-connected first while the drawn edges fit the budget; touched modules are always drawn."""

    def setUp(self):
        files = {f"{m}.py": (m,) for m in "tuabc"}
        base, head = d.Graph(files=dict(files)), d.Graph(files=dict(files))
        for g in (base, head):
            for src, dst in ("at", "au", "ta", "bt", "cu", "tu"):
                g.add(d.Edge((src,), (dst,), f"{src}.py", 1))
        self.bd = d.diff(base, head, {"t.py": (1, 0), "u.py": (0, 1)})

    def test_most_connected_context_first(self):
        self.assertEqual(render.drawn(self.bd, budget=4), ([("a",), ("t",), ("u",)], 2))

    def test_a_context_module_that_does_not_fit_stops_the_fill(self):
        self.assertEqual(render.drawn(self.bd, budget=3), ([("t",), ("u",)], 3))

    def test_touched_modules_are_drawn_even_over_budget(self):
        self.assertEqual(render.drawn(self.bd, budget=0), ([("t",), ("u",)], 3))

    def test_the_default_budget_draws_everything_here(self):
        self.assertEqual(render.drawn(self.bd)[1], 0)


class PaletteTest(unittest.TestCase):
    def test_override_one_token_in_one_mode(self):
        colors = render.palette({"light": {"add": "rgb(0, 128, 0)"}})
        self.assertEqual(colors["light"]["add"], "rgb(0, 128, 0)")
        self.assertEqual(colors["dark"]["add"], render.PALETTE["dark"]["add"])
        self.assertEqual(render.PALETTE["light"]["add"], "#1f8a4c")

    def test_unknown_mode_or_token_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "unknown token 'green'"):
            render.palette({"light": {"green": "#0f0"}})
        with self.assertRaisesRegex(ValueError, "not a mode"):
            render.palette({"sepia": {"add": "#0f0"}})

    def test_a_value_cannot_escape_the_style_element(self):
        for bad in ("red; } body { display: none", "#fff</style><script>", "url('x')", 7):
            with self.assertRaisesRegex(ValueError, "plain CSS color"):
                render.palette({"dark": {"bg": bad}})


if __name__ == "__main__":
    unittest.main()
