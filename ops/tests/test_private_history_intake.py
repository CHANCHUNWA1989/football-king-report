import copy
import unittest
from datetime import datetime, timezone
from ops.private_history_intake import validate, SCHEMA


class HistoryIntakeTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "source_namespace": "trusted_scores", "event_id": "match-1",
            "league_id": "epl", "home_team_id": "Team A",
            "away_team_id": "Team B", "kickoff_utc": "2026-01-01T12:00:00+00:00",
            "result_recorded_utc": "2026-01-01T15:00:00+00:00",
            "home_goals": 2, "away_goals": 1
        }
        self.data = {"schema": SCHEMA, "production_recommendations": "DISABLED",
                     "source": "private_history_provider",
                     "matches": [{**self.row, "event_id": f"match-{i}"} for i in range(30)]}

    def test_valid_shape(self):
        self.assertEqual(len(validate(self.data)), 30)

    def test_insufficient_history(self):
        self.data["matches"].pop()
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_duplicate_rejected(self):
        self.data["matches"][1] = copy.deepcopy(self.data["matches"][0])
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_future_result_rejected(self):
        self.data["matches"][0]["result_recorded_utc"] = "2026-01-01T11:00:00+00:00"
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_invalid_goals_rejected(self):
        self.data["matches"][0]["home_goals"] = True
        with self.assertRaises(ValueError):
            validate(self.data)

    def test_no_promotion(self):
        self.data["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            validate(self.data)


if __name__ == "__main__":
    unittest.main()
