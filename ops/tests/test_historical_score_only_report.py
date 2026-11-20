"""Synthetic regression tests for score-only history evaluation."""
import tempfile
import unittest
from pathlib import Path
from ops.historical_score_only_report import evaluate_results


class HistoricalScoreOnlyReportTests(unittest.TestCase):
    def evaluate(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.csv"
            path.write_text("Date,HomeTeam,AwayTeam,FTHG,FTAG\n" + rows, encoding="utf-8")
            return evaluate_results(path)

    def test_score_distribution(self):
        result = self.evaluate("2026-01-01,A,B,2,1\n2026-01-02,C,D,0,0\n")
        self.assertEqual(result["status"], "SCORE_ONLY_RESEARCH")
        self.assertEqual(result["matches"], 2)
        self.assertEqual(result["over_2_5"], 1)
        self.assertEqual(result["under_2_5"], 1)
        self.assertEqual(result["over_2_5_rate"], 0.5)
        self.assertEqual(result["draws"], 1)
        self.assertFalse(result["roi_available"])

    def test_duplicate_fixture_hold(self):
        result = self.evaluate("2026-01-01,A,B,2,1\n2026-01-01,A,B,2,1\n")
        self.assertEqual(result["status"], "HOLD")

    def test_invalid_score_hold(self):
        self.assertEqual(self.evaluate("2026-01-01,A,B,-1,0\n")["status"], "HOLD")

    def test_empty_hold(self):
        self.assertEqual(self.evaluate("")["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
