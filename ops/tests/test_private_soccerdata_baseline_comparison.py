import unittest
from ops.private_soccerdata_baseline_comparison import compare_to_frequency_baseline


def match(i, day, outcome):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T12:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "outcome": outcome}


class BaselineComparisonTests(unittest.TestCase):
    def setUp(self):
        self.history = [match(1, "2026-01-01", "H"), match(2, "2026-01-01", "H"),
                        match(3, "2026-01-02", "A"), match(4, "2026-01-03", "D")]
        self.forecasts = [
            {"fixture_id": "3", "outcome": "A",
             "probabilities": {"H": .2, "D": .2, "A": .6}},
            {"fixture_id": "4", "outcome": "D",
             "probabilities": {"H": .2, "D": .6, "A": .2}}]

    def test_paired_comparison_reports_descriptive_improvement(self):
        result = compare_to_frequency_baseline(self.history, self.forecasts,
                                                min_train=2, test_days=1)
        self.assertEqual(result["fixture_count"], 2)
        self.assertLess(result["log_loss_delta_challenger_minus_baseline"], 0)
        self.assertFalse(result["model_promoted"])

    def test_missing_fixture_rejected(self):
        with self.assertRaisesRegex(ValueError, "INCOMPLETE"):
            compare_to_frequency_baseline(self.history, self.forecasts[:1],
                                          min_train=2, test_days=1)

    def test_wrong_outcome_rejected(self):
        self.forecasts[0]["outcome"] = "H"
        with self.assertRaisesRegex(ValueError, "OUTCOME_MISMATCH"):
            compare_to_frequency_baseline(self.history, self.forecasts,
                                          min_train=2, test_days=1)

    def test_invalid_probabilities_rejected(self):
        self.forecasts[0]["probabilities"]["H"] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_CHALLENGER_PROBABILITIES"):
            compare_to_frequency_baseline(self.history, self.forecasts,
                                          min_train=2, test_days=1)


if __name__ == "__main__":
    unittest.main()
