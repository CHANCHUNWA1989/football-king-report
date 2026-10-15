import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_1x2_scoring import score

ROW = {
    "event_id": "fixture-1",
    "forecast_utc": "2026-10-14T12:00:00Z",
    "kickoff_utc": "2026-10-14T15:00:00Z",
    "settled_utc": "2026-10-14T18:00:00Z",
    "p_home": 0.6, "p_draw": 0.25, "p_away": 0.15,
    "result": "H",
}


class ShadowScoringTests(unittest.TestCase):
    def test_valid_prematch_settled_scoring(self):
        result = score([ROW])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["top_probability_accuracy"], 1.0)
        self.assertAlmostEqual(result["mean_brier"], 0.245)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_future_forecast_rejected(self):
        result = score([{**ROW, "forecast_utc": ROW["kickoff_utc"]}])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["status"], "HOLD")

    def test_invalid_probabilities_rejected(self):
        result = score([{**ROW, "p_home": 0.9}])
        self.assertEqual(result["accepted"], 0)

    def test_duplicate_event_rejected(self):
        result = score([ROW, ROW])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_empty_input_does_not_claim_skill(self):
        result = score([])
        self.assertIsNone(result["mean_log_loss"])
        self.assertFalse(result["minimum_sample_for_skill_claim_met"])


if __name__ == "__main__":
    unittest.main()
