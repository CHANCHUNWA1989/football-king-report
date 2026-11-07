import math
import unittest
from ops.private_soccerdata_team_poisson import evaluate_team_poisson


def row(i, day, hg, ag):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T00:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "home_team": "A", "away_team": "B", "home_goals": hg, "away_goals": ag,
            "outcome": "H" if hg > ag else "A" if hg < ag else "D"}


class TeamPoissonTests(unittest.TestCase):
    def setUp(self):
        self.records = [row(1, "2026-01-01", 2, 0), row(2, "2026-01-01", 1, 1),
                        row(3, "2026-01-02", 0, 1), row(4, "2026-01-03", 2, 1)]

    def test_actual_fitted_probabilities(self):
        result = evaluate_team_poisson(self.records, min_train=2, test_days=1)
        self.assertEqual(result["prediction_count"], 2)
        self.assertEqual(result["predictions"][0]["training_match_count"], 2)
        self.assertAlmostEqual(sum(result["predictions"][0]["probabilities"].values()), 1, places=8)
        self.assertTrue(math.isfinite(result["log_loss"]))
        self.assertFalse(result["positive_ev_verified"])

    def test_future_outcome_cannot_change_prior_forecast(self):
        a = evaluate_team_poisson(self.records, min_train=2, test_days=1)
        changed = [dict(r) for r in self.records]
        changed[-1]["home_goals"], changed[-1]["away_goals"], changed[-1]["outcome"] = 0, 3, "A"
        b = evaluate_team_poisson(changed, min_train=2, test_days=1)
        self.assertEqual(a["predictions"][0]["probabilities"], b["predictions"][0]["probabilities"])

    def test_inconsistent_score_rejected(self):
        self.records[0]["outcome"] = "D"
        with self.assertRaisesRegex(ValueError, "INVALID_SCORE_OR_TEAM"):
            evaluate_team_poisson(self.records, min_train=2)

    def test_insufficient_history_hold(self):
        self.assertEqual(evaluate_team_poisson(self.records, min_train=30)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
