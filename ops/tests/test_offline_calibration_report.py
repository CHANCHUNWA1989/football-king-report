"""Offline synthetic calibration metric tests."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_calibration_report import evaluate_binary_calibration


class TestOfflineCalibration(unittest.TestCase):
    def setUp(self):
        self.rows = [{"event_id": f"match-{i}", "probability": 0.8,
                      "outcome": 1 if i < 24 else 0} for i in range(30)]

    def test_known_brier_and_calibration(self):
        result = evaluate_binary_calibration(self.rows)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["sample_count"], 30)
        self.assertEqual(result["brier_score"], 0.16)
        self.assertEqual(result["calibration_bins"][0]["observed_rate"], 0.8)
        self.assertFalse(result["positive_ev_verified"])

    def test_small_sample_holds(self):
        self.assertEqual(evaluate_binary_calibration(self.rows[:29])["status"], "HOLD")

    def test_duplicate_event_holds(self):
        self.assertEqual(evaluate_binary_calibration(self.rows + [self.rows[0]])["status"], "HOLD")

    def test_invalid_probability_and_outcome_hold(self):
        for change in ({"probability": float("nan")}, {"probability": 1.1},
                       {"probability": True}, {"outcome": True}, {"outcome": 2}):
            with self.subTest(change=change):
                rows = [*self.rows]
                rows[0] = {**rows[0], **change}
                self.assertEqual(evaluate_binary_calibration(rows)["status"], "HOLD")

    def test_invalid_bins_hold(self):
        self.assertEqual(evaluate_binary_calibration(self.rows, bins=1)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
