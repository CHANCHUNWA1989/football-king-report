import unittest
from ops.private_soccerdata_frequency_baseline import evaluate_frequency_baseline


def row(i, day, outcome):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T12:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "outcome": outcome}


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(1, "2026-01-01", "H"), row(2, "2026-01-01", "H"),
                     row(3, "2026-01-02", "A"), row(4, "2026-01-03", "D")]

    def test_actual_holdout_forecasts_use_only_past(self):
        result = evaluate_frequency_baseline(self.rows, min_train=2, test_days=1)
        self.assertEqual(result["prediction_count"], 2)
        first = result["predictions"][0]
        self.assertEqual(first["fixture_id"], "3")
        self.assertAlmostEqual(first["probabilities"]["H"], 3 / 5)
        self.assertAlmostEqual(first["probabilities"]["A"], 1 / 5)
        self.assertEqual(first["training_match_count"], 2)
        self.assertGreater(result["log_loss"], 0)
        self.assertFalse(result["positive_ev_verified"])

    def test_insufficient_history_does_not_fabricate_scores(self):
        result = evaluate_frequency_baseline(self.rows, min_train=30)
        self.assertEqual(result["reason"], "INSUFFICIENT_HOLDOUT")

    def test_invalid_smoothing_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_frequency_baseline(self.rows, min_train=2, smoothing=0)

    def test_same_day_not_in_training(self):
        rows = self.rows + [row(5, "2026-01-02", "H")]
        result = evaluate_frequency_baseline(rows, min_train=2, test_days=1)
        first = [p for p in result["predictions"] if p["fixture_id"] == "3"][0]
        self.assertEqual(first["training_match_count"], 2)


if __name__ == "__main__":
    unittest.main()
