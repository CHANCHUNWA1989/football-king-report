import math
import unittest
from ops.private_soccerdata_dc_research import evaluate_dixon_coles_correction, _estimate_rho, _tau
from ops.private_soccerdata_team_poisson import evaluate_team_poisson


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

    def test_corrected_core_version_is_carried_into_dc_lineage(self):
        report = evaluate_dixon_coles_correction(self.records, min_train=2, test_days=1)
        self.assertIn("base_model", report)
        self.assertEqual(report["base_model"], "retrospective_team_goal_poisson_adaptive_tail_v2")
        self.assertEqual(report["model"], "approximate_low_score_dixon_coles_admissible_rho_v3")
        self.assertFalse(report["positive_ev_verified"])

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

    def test_no_low_score_evidence_keeps_neutral_rho(self):
        training = [{"home_goals": 2, "away_goals": 2},
                    {"home_goals": 4, "away_goals": 3}]
        for home_rate, away_rate in ((1, 1), (15, 15), (.05, 30)):
            with self.subTest(home_rate=home_rate, away_rate=away_rate):
                self.assertEqual(_estimate_rho(training, home_rate, away_rate), 0.0)

    def test_unseen_low_score_cells_must_all_have_positive_factors(self):
        for score in ((0, 0), (0, 1), (1, 0), (1, 1)):
            for home_rate, away_rate in ((15, 15), (30, .05), (.05, 30)):
                with self.subTest(score=score, home_rate=home_rate, away_rate=away_rate):
                    training = [{"home_goals": score[0], "away_goals": score[1]}]
                    rho = _estimate_rho(training, home_rate, away_rate)
                    for h, a in ((0, 0), (0, 1), (1, 0), (1, 1)):
                        factor = _tau(h, a, home_rate, away_rate, rho)
                        self.assertTrue(math.isfinite(factor) and factor > 0)

    def test_informative_training_can_still_select_nonzero_rho(self):
        for score, expected in (((0, 0), -.1), ((0, 1), .1),
                                ((1, 0), .1), ((1, 1), -.1)):
            with self.subTest(score=score):
                training = [{"home_goals": score[0], "away_goals": score[1]}]
                self.assertEqual(_estimate_rho(training, 1, 1), expected)

    def test_uninformative_fold_matches_poisson_without_mutating_history(self):
        records = [row(1, "2026-01-01", 2, 2), row(2, "2026-01-01", 3, 3),
                   row(3, "2026-01-02", 1, 0)]
        original = [dict(r) for r in records]
        baseline = evaluate_team_poisson(records, min_train=2, test_days=1)
        report = evaluate_dixon_coles_correction(records, min_train=2, test_days=1)
        prediction = report["predictions"][0]
        self.assertEqual(prediction["training_only_rho"], 0.0)
        for outcome in ("H", "D", "A"):
            self.assertAlmostEqual(prediction["probabilities"][outcome],
                                   baseline["predictions"][0]["probabilities"][outcome], places=14)
        self.assertEqual(records, original)
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["model_promoted"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_high_rate_fold_refuses_positive_rho_with_negative_zero_zero_cell(self):
        records = [row(1, "2026-01-01", 15, 15), row(2, "2026-01-01", 15, 15),
                   row(3, "2026-01-01", 0, 1), row(4, "2026-01-02", 1, 0)]
        report = evaluate_dixon_coles_correction(records, min_train=3, test_days=1)
        prediction = report["predictions"][0]
        self.assertEqual(prediction["training_only_rho"], 0.0)
        self.assertTrue(all(math.isfinite(v) and 0 <= v <= 1
                            for v in prediction["probabilities"].values()))
        self.assertAlmostEqual(sum(prediction["probabilities"].values()), 1, places=12)


if __name__ == "__main__":
    unittest.main()
