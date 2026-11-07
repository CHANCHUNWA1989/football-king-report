import unittest
from unittest.mock import patch
from ops.private_soccerdata_holdout_scoring import score_holdout_folds


class HoldoutTests(unittest.TestCase):
    def setUp(self):
        self.report = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                       "models_fitted": False, "point_in_time_backtest_ready": False,
                       "fold_count": 1, "folds": [{
                           "train_ids": ["a", "b"], "test_ids": ["c"],
                           "train_last_local_day": "2026-01-01",
                           "test_first_local_day": "2026-01-02"}]}
        self.rows = [{"fixture_id": "c"}]

    @patch("ops.private_soccerdata_holdout_scoring.compare")
    def test_holdout_only_calls_paired_scoring(self, compare):
        compare.return_value = {"status": "RESEARCH_ONLY"}
        result = score_holdout_folds(self.report, self.rows, self.rows)
        self.assertEqual(result["holdout_fixture_count"], 1)
        self.assertFalse(result["model_promoted"])
        compare.assert_called_once()

    def test_training_fixture_forecast_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISMATCH"):
            score_holdout_folds(self.report, [{"fixture_id": "a"}], self.rows)

    def test_overlap_rejected(self):
        self.report["folds"][0]["train_ids"].append("c")
        with self.assertRaisesRegex(ValueError, "LEAKAGE"):
            score_holdout_folds(self.report, self.rows, self.rows)

    def test_empty_fold_report_rejected(self):
        self.report["folds"] = []
        self.report["fold_count"] = 0
        with self.assertRaisesRegex(ValueError, "NO_VALID"):
            score_holdout_folds(self.report, self.rows, self.rows)


if __name__ == "__main__":
    unittest.main()
