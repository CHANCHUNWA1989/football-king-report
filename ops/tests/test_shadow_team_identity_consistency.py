"""Regression: provider spellings must never split a single club into two teams.

All fixtures are SYNTHETIC, pre-match and outcome-blind; this does not
establish actual source authenticity, odds, value, or prediction performance.
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_forecast import predict_league
from team_identity import team_id


class ShadowTeamIdentityConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
        self.historical = []
        for i in range(36):
            self.historical.append({
                "date": (self.now - timedelta(days=i+1)).date().isoformat(),
                "home": "Manchester City", "away": "Arsenal",
                "status": "FINISHED", "score_ft": [1 + i % 4, i % 3],
                "kickoff_utc": None
            })
        self.future = {
            "date": "2026-10-10",
            "home": "Manchester City", "away": "Arsenal",
            "event_id": "provider-native-123",
            "kickoff_utc": "2026-10-10T12:00:00+00:00",
            "status": "SCHEDULED", "score_ft": None,
        }

    def test_mixed_provider_aliases_match_single_club_training_probability(self):
        pure = predict_league(self.historical + [self.future], "epl", self.now)
        self.assertEqual(len(pure), 1)
        history = []
        for i, row in enumerate(self.historical):
            history.append({
                **row,
                "home": "Man City" if i % 2 else "Manchester City FC",
                "away": "Arsenal FC" if i % 3 else "Arsenal",
            })
        future = {**self.future, "home": "Man City", "away": "Arsenal FC"}
        alias = predict_league(history + [future], "epl", self.now)
        self.assertEqual(len(alias), 1)
        self.assertEqual(
            [pure[0][k] for k in ("p_home", "p_draw", "p_away",
                                "expected_home_goals", "expected_away_goals")],
            [alias[0][k] for k in ("p_home", "p_draw", "p_away",
                                 "expected_home_goals", "expected_away_goals")])
        self.assertEqual(alias[0]["training_games"], 36)
        self.assertEqual(alias[0]["role_sample_quality"]["home_team_total_games"], 36)
        self.assertEqual(alias[0]["role_sample_quality"]["away_team_total_games"], 36)
        self.assertEqual(alias[0]["role_sample_quality"]["home_team_home_games"], 36)
        self.assertEqual(alias[0]["role_sample_quality"]["away_team_away_games"], 36)
        self.assertEqual(alias[0]["home"], "Man City")  # Source display retained.
        self.assertEqual(alias[0]["away"], "Arsenal FC")
        self.assertFalse(alias[0]["calibrated"])
        self.assertEqual(alias[0]["production_recommendations"], "DISABLED")

    def test_alias_duplicate_same_result_cannot_double_weight_training(self):
        first = self.historical[0]
        redundant = {**first, "home": "Man City", "away": "Arsenal FC"}
        base = predict_league(self.historical + [self.future], "epl", self.now)
        rows = self.historical + [redundant, self.future]
        alt = predict_league(rows, "epl", self.now)
        self.assertEqual(len(alt), 1)
        self.assertEqual(alt[0]["training_games"], 36)
        self.assertEqual(
            [base[0][k] for k in ("p_home", "p_draw", "p_away")],
            [alt[0][k] for k in ("p_home", "p_draw", "p_away")])

    def test_same_match_alias_conflicting_score_fails_closed(self):
        first = self.historical[0]
        conflicting = {
            **first, "home": "Man City", "away": "Arsenal FC",
            "score_ft": [9, 9],
        }
        self.assertEqual(
            predict_league(self.historical + [conflicting, self.future], "epl", self.now),
            [])

    def test_same_scheduled_match_two_native_ids_fail_closed(self):
        second = {
            **self.future, "home": "Man City", "away": "Arsenal FC",
            "event_id": "provider-native-999",
        }
        self.assertEqual(
            predict_league(self.historical + [self.future, second], "epl", self.now),
            [])

    def test_same_scheduled_match_conflicting_kickoff_fails_closed(self):
        second = {
            **self.future, "home": "Man City", "away": "Arsenal FC",
            "event_id": "provider-native-999",
            "kickoff_utc": "2026-10-10T14:00:00+00:00",
        }
        self.assertEqual(
            predict_league(self.historical + [self.future, second], "epl", self.now),
            [])

    def test_home_away_aliases_of_same_club_rejected(self):
        invalid = {
            **self.future, "home": "Manchester City", "away": "Man City",
        }
        self.assertEqual(predict_league(self.historical + [invalid], "epl", self.now), [])

    def test_league_scoped_identity_never_spreads_aliases(self):
        self.assertEqual(team_id("epl", "Man City"), team_id("epl", "Manchester City"))
        self.assertNotEqual(team_id("championship", "Man City"),
                            team_id("championship", "Manchester City"))

    def test_home_and_away_role_orientation_remains_correct_with_aliases(self):
        history = []
        for i in range(36):
            history.append({
                "date": (self.now - timedelta(days=i+1)).date().isoformat(),
                "home": "Man City" if i % 2 else "Manchester City",
                "away": "Arsenal FC" if i % 2 else "Arsenal",
                "score_ft": [4, 0], "status": "FINISHED", "kickoff_utc": None,
            })
        for i in range(36):
            history.append({
                "date": (self.now - timedelta(days=i+37)).date().isoformat(),
                "home": "Arsenal", "away": "Manchester City FC",
                "score_ft": [0, 3], "status": "FINISHED", "kickoff_utc": None,
            })
        reverse = {
            **self.future, "home": "Arsenal FC", "away": "Man City",
            "event_id": "reverse-456",
            "kickoff_utc": "2026-10-10T14:00:00+00:00",
        }
        predicted = predict_league(history + [self.future, reverse], "epl", self.now)
        self.assertEqual(len(predicted), 2)
        by_id = {r["event_id"]: r for r in predicted}
        self.assertGreater(by_id[self.future["event_id"]]["p_home"],
                           by_id[self.future["event_id"]]["p_away"])
        self.assertGreater(by_id[reverse["event_id"]]["p_away"],
                           by_id[reverse["event_id"]]["p_home"])
        for case in predicted:
            self.assertEqual(case["production_recommendations"], "DISABLED")
            self.assertTrue(
                case["role_sample_quality"]["role_sample_sufficient_for_research"])


if __name__ == "__main__":
    unittest.main()
