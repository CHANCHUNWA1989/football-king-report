import unittest
from ops.private_offline_scoring import score

def row(fixture="test-1", outcome="H"):
    return {"fixture_id": fixture, "probabilities": {"H": 0.5, "D": 0.3, "A": 0.2},
            "outcome": outcome, "prediction_utc": "2026-01-01T10:00:00Z",
            "kickoff_utc": "2026-01-01T12:00:00Z",
            "result_recorded_utc": "2026-01-01T15:00:00Z"}

class ScoringTests(unittest.TestCase):
    def test_known_metrics(self):
        result = score([row()])
        self.assertAlmostEqual(result["log_loss"], 0.693147, places=5)
        self.assertAlmostEqual(result["multiclass_brier_score"], 0.38)
        self.assertEqual(sum(b["count"] for b in result["calibration"]), 3)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])

    def test_duplicate_fails(self):
        with self.assertRaises(ValueError):
            score([row(), row()])

    def test_future_result_does_not_retroactively_validate_prediction(self):
        data = row()
        data["prediction_utc"] = "2026-01-01T13:00:00Z"
        with self.assertRaises(ValueError):
            score([data])

    def test_invalid_probabilities(self):
        data = row()
        data["probabilities"]["H"] = float("nan")
        with self.assertRaises(ValueError):
            score([data])

    def test_missing_result_rejected(self):
        data = row()
        del data["outcome"]
        with self.assertRaises(ValueError):
            score([data])

if __name__ == "__main__":
    unittest.main()
