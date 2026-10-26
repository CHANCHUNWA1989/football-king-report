"""Synthetic tests for timestamped pre-match probability evaluation."""
import tempfile
import unittest
from pathlib import Path
from ops.historical_prematch_totals_evaluation import evaluate


class HistoricalPrematchTotalsEvaluationTests(unittest.TestCase):
    def run_rows(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            path.write_text("prediction_time,kickoff_time,home_goals,away_goals,predicted_over_2_5\n" + rows, encoding="utf-8")
            return evaluate(path)

    def test_valid_prematch(self):
        result = self.run_rows("2026-10-23T12:00:00+00:00,2026-10-24T12:00:00+00:00,2,1,0.75\n")
        self.assertEqual(result["status"], "OFFLINE_EVALUATION_ONLY")
        self.assertEqual(result["valid_rows"], 1)
        self.assertEqual(result["threshold_accuracy"], 1.0)
        self.assertIsNone(result["roi"])

    def test_post_kickoff_rejected(self):
        result = self.run_rows("2026-10-24T12:00:00+00:00,2026-10-24T12:00:00+00:00,2,1,0.75\n")
        self.assertEqual(result["status"], "HOLD")

    def test_naive_timestamp_rejected(self):
        result = self.run_rows("2026-10-23T12:00:00,2026-10-24T12:00:00,2,1,0.75\n")
        self.assertEqual(result["status"], "HOLD")

    def test_invalid_probability_rejected(self):
        result = self.run_rows("2026-10-23T12:00:00+00:00,2026-10-24T12:00:00+00:00,2,1,1.5\n")
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
