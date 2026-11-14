import unittest
from unittest.mock import patch
from ops.private_soccerdata_model_bridge import join_outcomes_and_compare


class ModelBridgeTests(unittest.TestCase):
    def setUp(self):
        self.history = {"provider": "soccerdata.MatchHistory", "point_in_time_backtest_ready": False,
                        "count": 1, "records": [{"source": "soccerdata.MatchHistory",
                        "source_index": "fixture-a", "outcome": "H", "kickoff_time_verified": False,
                        "odds_capture_verified": False, "pre_match_features_verified": False}]}
        self.rows = [{"fixture_id": "fixture-a", "outcome": "H"}]

    @patch("ops.private_soccerdata_model_bridge.compare")
    def test_exact_join_calls_existing_scoring(self, comparison):
        comparison.return_value = {"status": "RESEARCH_ONLY"}
        result = join_outcomes_and_compare(self.history, self.rows, self.rows)
        self.assertEqual(result["historical_outcomes_joined"], 1)
        self.assertFalse(result["pre_match_provenance_independently_verified"])
        comparison.assert_called_once()

    def test_missing_forecast_rejected(self):
        with self.assertRaises(ValueError):
            join_outcomes_and_compare(self.history, [], [])

    def test_result_disagreement_rejected(self):
        with self.assertRaises(ValueError):
            join_outcomes_and_compare(self.history, [{"fixture_id": "fixture-a", "outcome": "A"}], self.rows)

    def test_false_history_provenance_rejected(self):
        self.history["records"][0]["odds_capture_verified"] = True
        with self.assertRaises(ValueError):
            join_outcomes_and_compare(self.history, self.rows, self.rows)


if __name__ == "__main__":
    unittest.main()
