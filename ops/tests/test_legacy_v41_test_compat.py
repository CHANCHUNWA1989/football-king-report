"""V4.1 compatibility adjustment is exact and never weakens HOLD."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from legacy_v41_test_compat import adapt, ORIGINAL, SAFER


class LegacyV41CompatTests(unittest.TestCase):
    def test_replace_only_known_obsolete_assertion(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / "tests").mkdir()
            target = app / "tests" / "test_verified.py"
            target.write_text("before\n" + ORIGINAL + "\nafter\n", encoding="utf-8")
            adapt(app)
            revised = target.read_text(encoding="utf-8")
            self.assertNotIn(ORIGINAL, revised)
            self.assertIn(SAFER, revised)
            self.assertIn("before", revised)
            self.assertIn("after", revised)

    def test_unknown_upstream_legacy_test_fails_loudly(self):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder)
            (app / "tests").mkdir()
            target = app / "tests" / "test_verified.py"
            target.write_text("assert False", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "UNEXPECTED_LEGACY_TEST_VERSION"):
                adapt(app)


if __name__ == "__main__":
    unittest.main()
