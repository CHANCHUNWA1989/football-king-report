import unittest
from ops.private_soccerdata_dc_research import evaluate_dixon_coles_correction, _tau


def row(i, day, h, a):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T00:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "home_team": "A", "away_team": "B", "home_goals": h, "away_goals": a,
            "outcome": "H" if h > a else "A" if h < a else "D"}


class DixonColesResearchTests(unittest.TestCase):
    def setUp(self):
        self.records = [row(1, "2026-01-01", 1, 0), row(2, "2026-01-01", 0, 1),
                        row(3, "2026-01-02", 0, 0), row(4, "2026-01-03", 1, 1)]

    def test_probabilities_normalized(self):
        r = evaluate_dixon_coles_correction(self.records, min_train=2, test_days=1)
        self.assertEqual(r["prediction_count"], 2)
        self.assertFalse(r["model_promoted"])
        for p in r["predictions"]:
            self.assertAlmostEqual(sum(p["probabilities"].values()), 1, places=8)

    def test_no_future_leakage(self):
        first = evaluate_dixon_coles_correction(self.records, min_train=2, test_days=1)
        modified = [dict(r) for r in self.records]
        modified[-1].update(home_goals=4, away_goals=0, outcome="H")
        second = evaluate_dixon_coles_correction(modified, min_train=2, test_days=1)
        self.assertEqual(first["predictions"][0]["probabilities"],
                         second["predictions"][0]["probabilities"])

    def test_tau_identity(self):
        self.assertEqual(_tau(0, 0, 1, 1, 0), 1)
        self.assertEqual(_tau(2, 2, 1, 1, -.1), 1)

    def test_insufficient_holdout(self):
        self.assertEqual(evaluate_dixon_coles_correction(self.records, min_train=50)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
