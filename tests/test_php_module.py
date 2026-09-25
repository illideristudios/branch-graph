"""The PHP language module: a file's namespace + filename is its module, `use` statements are the edges, exact match only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph.languages.php import MODULE as php  # noqa: E402

KNOWN = {
    ("App", "Foo"),
    ("App", "Foo", "Bar"),
    ("App", "Foo", "Sub", "Deep"),
    ("App", "Db", "query"),
    ("HasFoo",),
    ("legacy", "x"),
}


def imports(source, path="src/X.php"):
    return list(php.imports(path, ("App", "X"), source, KNOWN))


class ModuleOfTest(unittest.TestCase):
    def test_namespace_plus_filename(self):
        src = "<?php\nnamespace OpenEMR\\Common\\Database;\n\nclass QueryUtils {}\n"
        self.assertEqual(php.module_of("src/Common/Database/QueryUtils.php", "src", src), ("OpenEMR", "Common", "Database", "QueryUtils"))
        self.assertEqual(php.module_of("src/Common/Database/QueryUtils.php", ".", src), ("OpenEMR", "Common", "Database", "QueryUtils"))

    def test_braced_namespace(self):
        self.assertEqual(php.module_of("a/B.php", ".", "<?php\nnamespace App\\Foo {\n}\n"), ("App", "Foo", "B"))

    def test_no_namespace_is_its_path_under_root(self):
        legacy = "<?php\necho 1;\n"
        self.assertEqual(php.module_of("interface/patient_file/summary.php", ".", legacy), ("interface", "patient_file", "summary"))
        self.assertEqual(php.module_of("interface/patient_file/summary.php", "interface", legacy), ("patient_file", "summary"))
        self.assertEqual(php.module_of("library/options.inc.php", ".", legacy), ("library", "options.inc"))

    def test_namespace_in_a_comment_or_the_operator_is_not_a_declaration(self):
        src = "<?php\n// namespace Nope;\n/**\n * namespace Nope2;\n */\n$x = namespace\\foo();\n"
        self.assertEqual(php.module_of("a/B.php", ".", src), ("a", "B"))

    def test_claims_php_only(self):
        self.assertTrue(php.claims("a/B.php"))
        self.assertFalse(php.claims("a/B.py"))
        self.assertFalse(php.claims("a/B.phps.txt"))


class ImportsTest(unittest.TestCase):
    def test_plain_use_with_its_line(self):
        self.assertEqual(imports("<?php\nnamespace App;\n\nuse App\\Foo\\Bar;\n"), [(("App", "Foo", "Bar"), 4)])

    def test_alias_and_leading_backslash(self):
        self.assertEqual(imports("<?php\nuse App\\Foo\\Bar as B;\nuse \\App\\Foo;\n"), [(("App", "Foo", "Bar"), 2), (("App", "Foo"), 3)])

    def test_comma_list(self):
        self.assertEqual(imports("<?php\nuse App\\Foo, App\\Foo\\Bar as B;\n"), [(("App", "Foo"), 2), (("App", "Foo", "Bar"), 2)])

    def test_group_use_expands_and_takes_the_statements_first_line(self):
        src = "<?php\nuse App\\Foo\\{\n    Bar,\n    Sub\\Deep as D,\n    Missing,\n};\n"
        self.assertEqual(imports(src), [(("App", "Foo", "Bar"), 2), (("App", "Foo", "Sub", "Deep"), 2)])

    def test_function_and_const_imports_are_skipped(self):
        src = "<?php\nuse function App\\Db\\query;\nuse const App\\Foo\\Bar;\nuse App\\Db\\{function query};\n"
        self.assertEqual(imports(src), [])

    def test_third_party_dropped(self):
        self.assertEqual(imports("<?php\nuse Symfony\\Component\\Yaml\\Yaml;\n"), [])

    def test_exact_match_only_never_a_prefix(self):
        # App\Foo is a module, App\Foo\Missing is not: the name is unresolved, not an edge to App\Foo.
        self.assertEqual(imports("<?php\nuse App\\Foo\\Missing;\n"), [])

    def test_bare_name_closure_and_comments_are_not_imports(self):
        src = "<?php\nclass A {\n    use HasFoo;\n}\n$f = function () {\n    use ($x);\n};\n// use App\\Foo;\n/**\n * use App\\Foo\\Bar;\n */\n"
        self.assertEqual(imports(src), [])

    def test_crlf_lines_count_the_same(self):
        self.assertEqual(imports("<?php\r\nnamespace App;\r\n\r\nuse App\\Foo\\Bar;\r\n"), [(("App", "Foo", "Bar"), 4)])


if __name__ == "__main__":
    unittest.main()
