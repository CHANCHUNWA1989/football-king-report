"""Unified runner must remain HOLD with missing or invalid evidence."""
import sys
import csv
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_research import run


class UnifiedResearchTests(unittest.TestCase):
    def test_shared_cutoff_cohort_returns_hold_without_holdout_scores(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "synthetic.csv"
            fields = ["case_id", "prediction_utc", "market_utc", "kickoff_utc",
                      "p_home", "p_draw", "p_away", "m_home", "m_draw", "m_away", "outcome"]
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                for index, kickoff in enumerate(("2026-10-01T12:00:00Z", "2026-10-02T12:00:00Z",
                                                 "2026-10-03T12:00:00Z", "2026-10-03T12:00:00Z")):
                    writer.writerow([f"synthetic-{index}", "2026-10-01T10:00:00Z",
                                     "2026-10-01T09:59:00Z", kickoff,
                                     .7, .2, .1, .2, .2, .6, "away"])
            original = path.read_bytes()
            result = run(path)
            self.assertEqual(path.read_bytes(), original)
        self.assertIsNone(result["market_shrinkage"])
        self.assertEqual(result["reason"], "INVALID_RESEARCH_INPUT_ValueError")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

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
