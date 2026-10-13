"""Unified runner must remain HOLD with missing or invalid evidence."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_research import run


class UnifiedResearchTests(unittest.TestCase):
    def test_missing_input(self):
        with tempfile.TemporaryDirectory() as d:
            result = run(str(Path(d) / "missing.csv"))
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "NO_SEALED_PREDICTIONS")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_invalid_input(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.csv"
            path.write_text("not,a,valid,shadow,log\n", encoding="utf-8")
            result = run(str(path))
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["reason"].startswith("INVALID_RESEARCH_INPUT_"))


if __name__ == "__main__":
    unittest.main()
