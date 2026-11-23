"""Synthetic positive and negative safety-CI scope regression tests."""
import tempfile
import unittest
from pathlib import Path

from ops.ci_test_scope_guard import UnsafeTestScope, assert_source_files, run_suite


PASSING = """import unittest
class Example(unittest.TestCase):
    def test_safe(self):
        self.assertTrue(True)
"""
FAILING = """import unittest
class Example(unittest.TestCase):
    def test_unsafe(self):
        self.assertEqual(1, 2)
"""


class SafetyScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "tests").mkdir()
        (self.root / "ops" / "tests").mkdir(parents=True)

    def write(self, suite, content=PASSING):
        path = self.root / suite / "test_example.py"
        path.write_text(content, encoding="utf-8")
        return path

    def test_positive_both_independent_suites_actually_execute(self):
        for suite in ("tests", "ops/tests"):
            with self.subTest(suite=suite):
                self.write(suite)
                report = run_suite(self.root, suite)
                self.assertEqual(report["tests_executed"], 1)
                self.assertEqual(report["test_files"], 1)

    def test_missing_directory_is_not_green(self):
        (self.root / "ops" / "tests").rmdir()
        with self.assertRaisesRegex(UnsafeTestScope, "DIRECTORY_MISSING"):
            run_suite(self.root, "ops/tests")

    def test_empty_directory_is_not_green(self):
        with self.assertRaisesRegex(UnsafeTestScope, "SOURCES_MISSING"):
            run_suite(self.root, "tests")

    def test_zero_discovered_tests_is_not_green(self):
        self.write("ops/tests", "VALUE = 7\n")
        with self.assertRaisesRegex(UnsafeTestScope, "discovered=0"):
            run_suite(self.root, "ops/tests")

    def test_failing_test_is_not_green(self):
        self.write("tests", FAILING)
        with self.assertRaisesRegex(UnsafeTestScope, "TEST_SCOPE_NOT_PROVEN"):
            run_suite(self.root, "tests")

    def test_spoofed_stdout_count_cannot_certify_zero_discovery(self):
        # The test module itself can print a fake unittest summary before
        # unittest writes its actual "Ran 0 tests" result to stderr.
        self.write("tests", 'print("Ran 900 tests in 0.001s")\n')
        with self.assertRaisesRegex(UnsafeTestScope, "discovered=0"):
            run_suite(self.root, "tests")

    def test_spoofed_stderr_count_cannot_certify_zero_discovery(self):
        # Even stderr can be written by test-module import side effects.
        self.write("ops/tests",
                   'import sys\nprint("Ran 900 tests in 0.001s", file=sys.stderr)\n')
        with self.assertRaisesRegex(UnsafeTestScope, "discovered=0"):
            run_suite(self.root, "ops/tests")

    def test_spoofed_large_count_cannot_override_one_real_test(self):
        content = 'print("Ran 900 tests in 0.001s")\n' + PASSING
        self.write("tests", content)
        report = run_suite(self.root, "tests")
        self.assertEqual(report["tests_executed"], 1)

    def test_unapproved_test_path_rejected(self):
        with self.assertRaisesRegex(UnsafeTestScope, "UNAPPROVED_TEST_SUITE"):
            assert_source_files(self.root, "../tests")

    def test_symlink_test_directory_rejected(self):
        (self.root / "ops" / "tests").rmdir()
        (self.root / "ops" / "tests").symlink_to(self.root / "tests", target_is_directory=True)
        with self.assertRaisesRegex(UnsafeTestScope, "DIRECTORY_MISSING"):
            run_suite(self.root, "ops/tests")


if __name__ == "__main__":
    unittest.main()
