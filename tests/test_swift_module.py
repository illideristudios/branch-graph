"""The Swift language module: a file belongs to its target, and `import` lines name targets."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))

from branch_graph.languages.swift import MODULE as swift  # noqa: E402

KNOWN = {("App",), ("Core",), ("Net",), ("CoreTests",)}


class ModuleOfTest(unittest.TestCase):
    def test_swiftpm_target_is_the_directory_under_sources_or_tests(self):
        self.assertEqual(swift.module_of("Sources/Core/Models/User.swift", "."), ("Core",))
        self.assertEqual(swift.module_of("Tests/CoreTests/UserTests.swift", "."), ("CoreTests",))
        self.assertEqual(swift.module_of("Packages/Kit/Sources/Net/Client.swift", "."), ("Net",))

    def test_otherwise_the_first_directory_under_the_root(self):
        self.assertEqual(swift.module_of("ios/App/Views/Home.swift", "ios"), ("App",))
        self.assertEqual(swift.module_of("main.swift", "."), ("main",))

    def test_the_manifest_is_not_a_module(self):
        self.assertIsNone(swift.module_of("Package.swift", "."))
        self.assertIsNone(swift.module_of("Package@swift-5.9.swift", "."))

    def test_claims(self):
        self.assertTrue(swift.claims("a.swift"))
        self.assertFalse(swift.claims("a.swiftinterface"))


class ImportsTest(unittest.TestCase):
    def imports(self, source, module=("App",)):
        return list(swift.imports("Sources/App/x.swift", module, source, KNOWN))

    def test_plain_import_with_its_line_and_system_modules_dropped(self):
        self.assertEqual(self.imports("import Foundation\nimport SwiftUI\n\nimport Core\n"), [(("Core",), 4)])

    def test_attributes_access_levels_and_kinds(self):
        src = "@testable import Core\npublic import Net\n@_exported import App\nimport struct Core.User\n@preconcurrency internal import Net.HTTP\n"
        self.assertEqual(self.imports(src, ("CoreTests",)), [(("Core",), 1), (("Net",), 2), (("App",), 3), (("Core",), 4), (("Net",), 5)])

    def test_not_an_import(self):
        self.assertEqual(self.imports("// import Core\nlet importance = 1\nimportCore()\n"), [])


if __name__ == "__main__":
    unittest.main()
