import unittest
from ops.league_goal_blend_real_replay import (
    _rows, _season_quality, replay_pair, SOURCE_SHA,
)
from ops.league_goal_blend_shadow import audit


def season(year):
    teams = [f"Team{i}" for i in range(6)]
    result = []
    for i, home in enumerate(teams):
        for j, away in enumerate(teams):
            if i == j:
                continue
            result.append({"home": home, "away": away,
                           "date": f"{year}-05-01",
                           "home_goals": (i+j) % 4, "away_goals": (i+j+1) % 3})
    return result


class LeagueRealReplayTests(unittest.TestCase):
    def test_complete_synthetic_home_away_season(self):
        self.assertTrue(_season_quality(season(2024), 6))
        self.assertFalse(_season_quality(season(2024)[:-1], 6))
        self.assertFalse(_season_quality(season(2024), 20))

    def test_duplicate_home_away_pair_rejected(self):
        rows = season(2024)
        rows[1] = dict(rows[0])
        self.assertFalse(_season_quality(rows, 6))

    def test_real_original_model_api_replayed_without_test_scores(self):
        fold = replay_pair(season(2024), season(2025), "epl", "2023-24", "2024-25")
        self.assertEqual(len(fold["heldout"]), 30)
        self.assertEqual(len(fold["training"]), 30)
        self.assertTrue(all(0.1 <= x["expected_home_goals"] <= 5.5
                            for x in fold["heldout"]))
        report = audit([fold], source_revision=SOURCE_SHA)
        self.assertEqual(report["pooled"]["OVER25"]["sample_count"], 30)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["eligible_for_model_promotion"])

    def test_replay_does_not_use_heldout_score_as_predictor(self):
        original = season(2025)
        a = replay_pair(season(2024), original, "epl", "2023-24", "2024-25")
        reversed_scores = [{**x, "home_goals": 7, "away_goals": 5}
                           for x in original]
        b = replay_pair(season(2024), reversed_scores, "epl", "2023-24", "2024-25")
        a_rates = [(x["expected_home_goals"], x["expected_away_goals"])
                   for x in a["heldout"]]
        b_rates = [(x["expected_home_goals"], x["expected_away_goals"])
                   for x in b["heldout"]]
        self.assertEqual(a_rates, b_rates)

    def test_openfootball_score_shapes_and_invalid_input(self):
        sample = {"matches": [
            {"team1": "A", "team2": "B", "date": "2024-08-09", "score": [2, 1]},
            {"team1": "C", "team2": "D", "date": "2024-08-10", "score": {"ft": [0, 0]}},
            {"team1": "E", "team2": "F", "date": "2024-08-11", "score": None},
        ]}
        self.assertEqual(len(_rows(sample)), 2)
        with self.assertRaisesRegex(ValueError, "INVALID_ARCHIVE_SCHEMA"):
            _rows({"matches": None})
        sample["matches"][0]["score"] = [True, 0]
        self.assertEqual(len(_rows(sample)), 1)

    def test_duplicate_replay_event_identity_fails_closed(self):
        rows = season(2025)
        rows[1] = {**rows[0]}
        with self.assertRaisesRegex(ValueError, "DUPLICATE_REPLAY_ID"):
            replay_pair(season(2024), rows, "epl", "2023-24", "2024-25")


if __name__ == "__main__":
    unittest.main()
