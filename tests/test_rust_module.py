"""The Rust language module: a file belongs to its crate path, and `use` trees name modules."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph import languages  # noqa: E402
from branch_graph.languages.rust import MODULE as rust  # noqa: E402
from branch_graph.use_case import build_graph  # noqa: E402

KNOWN = {("app",), ("app", "db"), ("app", "net"), ("app", "net", "http"), ("domain",), ("domain", "model")}
MANIFESTS = {
    "Cargo.toml": '[package]\nname = "my-tool"\n',
    "crates/x/Cargo.toml": '[package]\nname = "x"\n[lib]\nname = "x_lib"\n',
    "ws/Cargo.toml": "[workspace]\nmembers = []\n",
    "bad/Cargo.toml": "not = [toml",
}


class ModuleOfTest(unittest.TestCase):
    def test_crate_plus_path_under_src(self):
        self.assertEqual(rust.module_of("crates/app/src/net/http.rs", "."), ("app", "net", "http"))
        self.assertEqual(rust.module_of("crates/my-domain/src/model.rs", "."), ("my_domain", "model"))

    def test_lib_main_and_mod_name_their_directory(self):
        self.assertEqual(rust.module_of("crates/app/src/lib.rs", "."), ("app",))
        self.assertEqual(rust.module_of("crates/app/src/main.rs", "."), ("app",))
        self.assertEqual(rust.module_of("crates/app/src/net/mod.rs", "."), ("app", "net"))

    def test_root_crate_and_other_trees(self):
        self.assertEqual(rust.module_of("src/lib.rs", "."), ("crate",))
        self.assertEqual(rust.module_of("rust/src/x.rs", "rust"), ("rust", "x"))
        self.assertEqual(rust.module_of("crates/app/tests/smoke.rs", "."), ("app", "tests", "smoke"))

    def test_root_inside_the_crate_still_names_it(self):
        self.assertEqual(rust.module_of("src/lib.rs", "src"), ("crate",))
        self.assertEqual(rust.module_of("src/net/http.rs", "src"), ("crate", "net", "http"))

    def test_nearest_src_names_the_crate_and_targets_drop_mod_and_main(self):
        self.assertEqual(rust.module_of("examples/demo/src/main.rs", "."), ("demo",))
        self.assertEqual(rust.module_of("crates/app/tests/fixture/src/lib.rs", "."), ("fixture",))
        self.assertEqual(rust.module_of("crates/app/src/tests/x.rs", "."), ("app", "tests", "x"))
        self.assertEqual(rust.module_of("crates/app/tests/common/mod.rs", "."), ("app", "tests", "common"))
        self.assertEqual(rust.module_of("crates/app/examples/cli/main.rs", "."), ("app", "examples", "cli"))
        self.assertEqual(rust.module_of("crates/app/src/bin/tool/main.rs", "."), ("app", "bin", "tool"))
        self.assertEqual(rust.module_of("crates/app/src/net/main.rs", "."), ("app", "net", "main"))

    def test_cargo_toml_names_the_crate(self):
        named = rust.configured(MANIFESTS)
        self.assertEqual(named.module_of("src/main.rs", "."), ("my_tool",))
        self.assertEqual(named.module_of("tests/smoke.rs", "."), ("my_tool", "tests", "smoke"))
        self.assertEqual(named.module_of("crates/x/src/a.rs", "."), ("x_lib", "a"))
        self.assertEqual(named.module_of("crates/y/src/a.rs", "."), ("y", "a"))

    def test_build_script_is_not_a_module(self):
        self.assertIsNone(rust.module_of("build.rs", "."))
        self.assertIsNone(rust.module_of("crates/app/build.rs", "."))

    def test_claims(self):
        self.assertTrue(rust.claims("a.rs"))
        self.assertFalse(rust.claims("a.rsx"))


class ImportsTest(unittest.TestCase):
    def imports(self, source, module=("app", "net"), path="crates/app/src/net/mod.rs", known=KNOWN):
        return list(rust.imports(path, module, source, known))

    def test_crate_super_self_and_bare_paths_with_their_lines(self):
        src = "use std::io;\nuse crate::db::Pool;\nuse super::db;\nuse self::http::Client;\nuse http::Server;\nuse domain::model::User;\n"
        self.assertEqual(
            self.imports(src),
            [(("app", "db"), 2), (("app", "db"), 3), (("app", "net", "http"), 4), (("app", "net", "http"), 5), (("domain", "model"), 6)],
        )

    def test_nested_trees_aliases_and_globs(self):
        src = "use crate::{\n    db::*,\n    net::http::{self, Client as C},\n};\n"
        self.assertEqual(self.imports(src, ("app",)), [(("app", "db"), 1), (("app", "net", "http"), 1), (("app", "net", "http"), 1)])

    def test_super_super_reaches_the_crate_root(self):
        self.assertEqual(self.imports("use super::super::Config;\n", ("app", "net", "http")), [(("app",), 1)])

    def test_visibility_and_use_inside_a_body(self):
        self.assertEqual(self.imports("pub(crate) use ::domain::model;\nfn f() { use crate::db; }\n"), [(("domain", "model"), 1), (("app", "db"), 2)])

    def test_inline_mod_is_one_level_down_for_super(self):
        src = "pub struct Client;\n#[cfg(test)]\nmod tests {\n    use super::*;\n    use super::super::super::db;\n}\n"
        self.assertEqual(self.imports(src, ("app", "net", "http")), [(("app", "db"), 5)])

    def test_crate_in_a_binary_means_that_binary(self):
        known = KNOWN | {("app", "cli"), ("app", "bin", "tool"), ("app", "bin", "tool", "cli")}
        src = "use crate::cli;\nuse app::cli::Args;\n"
        self.assertEqual(self.imports(src, ("app", "bin", "tool"), "crates/app/src/bin/tool/main.rs", known), [(("app", "bin", "tool", "cli"), 1), (("app", "cli"), 2)])
        # A one-file binary's crate is src/bin/ itself: its `crate::cli` is src/bin/cli.rs, never the library's.
        self.assertEqual(self.imports(src, ("app", "bin", "tool"), "crates/app/src/bin/tool.rs", known), [(("app", "cli"), 2)])
        # Its unit tests' `super::*` is the binary itself, not a way out to the library root.
        tests = "fn main() {}\n#[cfg(test)]\nmod tests {\n    use super::*;\n}\n"
        self.assertEqual(self.imports(tests, ("app", "bin", "tool"), "crates/app/src/bin/tool.rs", known), [])

    def test_test_crate_reaches_its_shared_helper(self):
        known = {("app",), ("app", "tests", "smoke"), ("app", "tests", "common")}
        src = "mod common;\nuse common::helper;\nuse crate::common::x;\n"
        self.assertEqual(self.imports(src, ("app", "tests", "smoke"), "crates/app/tests/smoke.rs", known), [(("app", "tests", "common"), 2), (("app", "tests", "common"), 3)])

    def test_main_reaches_its_library_by_package_name_and_externals_stay_out(self):
        named = rust.configured(MANIFESTS)
        known = {("my_tool",), ("my_tool", "config"), ("my_tool", "io")}
        src = "use my_tool::config::Config;\nuse tokio::io::AsyncRead;\nuse std::io;\n"
        self.assertEqual(list(named.imports("src/main.rs", ("my_tool",), src, known)), [(("my_tool", "config"), 1)])

    def test_root_inside_the_crate_resolves_crate_paths(self):
        known = {("crate",), ("crate", "db"), ("crate", "net", "http")}
        self.assertEqual(self.imports("use crate::db::Pool;\n", ("crate", "net", "http"), "src/net/http.rs", known), [(("crate", "db"), 1)])

    def test_raw_identifiers_match_their_module(self):
        self.assertEqual(self.imports("use crate::r#async::Task;\n", known=KNOWN | {("app", "async")}), [(("app", "async"), 1)])

    def test_unbalanced_braces_do_not_fail_the_run(self):
        self.assertEqual(self.imports("use foo::{a::{b};\nuse crate::db;\n"), [(("app", "db"), 2)])

    def test_r_inside_a_string_and_nested_comments_are_not_code(self):
        src = 'fn a() { print!("\\r"); let c = \'"\'; }\n/* a /* b */ use crate::net::http; */\nuse crate::db;\n'
        self.assertEqual(self.imports(src), [(("app", "db"), 3)])

    def test_not_an_import_or_a_self_edge(self):
        src = '// use crate::db;\nlet s = "use crate::db;";\nfn reuse() {}\nuse crate::net::Thing;\nuse missing::X;\n'
        self.assertEqual(self.imports(src), [])


class BuildGraphTest(unittest.TestCase):
    def test_cargo_toml_names_reach_the_graph(self):
        class Source:
            files_ = {**MANIFESTS, "src/lib.rs": "pub mod config;\n", "src/config.rs": "", "src/main.rs": "use my_tool::config;\n"}

            def files(self, rev, root):
                return [p for p in self.files_ if root == "." or p.startswith(root + "/")]

            def read_all(self, rev, paths):
                return {p: self.files_[p] for p in paths}

        graph = build_graph(Source(), languages.selector(languages.load()), "HEAD", "src")
        self.assertEqual(set(graph.edges), {(("my_tool",), ("my_tool", "config"))})


class ClassesTest(unittest.TestCase):
    def test_types_and_impls_through_attributes_lifetimes_and_raw_strings(self):
        src = (
            "#[derive(Debug, Clone)] pub struct User {\n"
            "    name: String,\n"
            "}\n"
            "\n"
            "pub(crate) enum Role { Admin, Guest }\n"
            "struct Marker;\n"
            "\n"
            "impl<'a, T: Into<String>> Display for Wrapper<'a, T> where T: Fn() -> u8 {\n"
            '    fn fmt(&self) -> &\'a str { r#"}"# }\n'
            "}\n"
            "trait Shape {\n"
            "    fn area(&self) -> f64;\n"
            "}\n"
            "impl User {\n"
            "    fn initial(&self) -> char { '}' }\n"
            "}\n"
        )
        self.assertEqual(rust.classes(src), [("User", 1, 3), ("Role", 5, 5), ("Wrapper", 8, 10), ("Shape", 11, 13), ("User", 14, 16)])

    def test_impl_names_past_where_clauses_paths_dyn_tuples_and_higher_ranked_bounds(self):
        src = (
            "impl<T> Show for Foo<T> where T: for<'a> Fn(&'a u8) {\n}\n"
            "impl Show for io::Bar {\n}\n"
            "impl dyn Shape + Send {\n}\n"
            "impl Show for (A, B) {\n}\n"
            'fn a() { print!("\\r"); }\nimpl Baz {\n}\n'
            "impl Tr for Vec<Box<dyn for<'a> Fn(&'a u8)>> {\n}\n"
        )
        self.assertEqual([name for name, _, _ in rust.classes(src)], ["Foo", "Bar", "Shape", "(A, B)", "Baz", "Vec"])


if __name__ == "__main__":
    unittest.main()
