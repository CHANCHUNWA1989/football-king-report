import math
import unittest
from ops.private_soccerdata_team_poisson import _poisson, evaluate_team_poisson


def reference_probabilities(home_rate, away_rate):
    # Independent log-PMF oracle, not the model's recurrence or truncation.
    home = [math.exp(-home_rate + k * math.log(home_rate) - math.lgamma(k + 1))
            for k in range(121)]
    away = [math.exp(-away_rate + k * math.log(away_rate) - math.lgamma(k + 1))
            for k in range(121)]
    return {
        "H": math.fsum(p * math.fsum(away[:h]) for h, p in enumerate(home)),
        "D": math.fsum(h * a for h, a in zip(home, away)),
        "A": math.fsum(p * math.fsum(home[:a]) for a, p in enumerate(away)),
    }


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

    def test_high_rate_tail_is_not_collapsed_into_twelve_goal_bin(self):
        actual = _poisson(15)
        expected_at_twelve = math.exp(-15 + 12 * math.log(15) - math.lgamma(13))
        self.assertAlmostEqual(actual[12], expected_at_twelve, places=11)
        self.assertGreater(len(actual), 13)
        self.assertAlmostEqual(math.fsum(actual), 1, places=14)

    def test_core_predictions_match_independent_poisson_at_rate_boundaries(self):
        for home_rate, away_rate in ((15, 15), (15, 3), (3, 15), (2, 1)):
            with self.subTest(home_rate=home_rate, away_rate=away_rate):
                records = [row(1, "2026-01-01", home_rate, away_rate),
                           row(2, "2026-01-01", home_rate, away_rate),
                           row(3, "2026-01-02", 1, 0)]
                original = [dict(r) for r in records]
                report = evaluate_team_poisson(records, min_train=2, test_days=1)
                actual = report["predictions"][0]["probabilities"]
                expected = reference_probabilities(home_rate, away_rate)
                for outcome in ("H", "D", "A"):
                    self.assertAlmostEqual(actual[outcome], expected[outcome], places=10)
                self.assertAlmostEqual(math.fsum(actual.values()), 1, places=12)
                self.assertEqual(records, original)
                self.assertFalse(report["model_promoted"])
                self.assertFalse(report["positive_ev_verified"])

    def test_new_outputs_identify_tail_corrected_model_without_promotion(self):
        report = evaluate_team_poisson(self.records, min_train=2, test_days=1)
        self.assertEqual(report["model"], "retrospective_team_goal_poisson_adaptive_tail_v2")
        self.assertEqual(report["per_team_omitted_tail_mass_bound"], 1e-12)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["independent_provenance_verified"])

    def test_poisson_mass_remains_nonnegative_finite_and_normalized(self):
        for rate in (0, .05, .1, 1, 5.5, 15):
            with self.subTest(rate=rate):
                values = _poisson(rate)
                self.assertTrue(all(math.isfinite(p) and p >= 0 for p in values))
                self.assertAlmostEqual(math.fsum(values), 1, places=14)
                self.assertAlmostEqual(values[0], math.exp(-rate), places=11)

    def test_actual_omitted_tail_satisfies_declared_bound(self):
        for rate in (.05, 1, 5.5, 15):
            with self.subTest(rate=rate):
                values = _poisson(rate)
                omitted = math.fsum(math.exp(-rate + k * math.log(rate) - math.lgamma(k + 1))
                                    for k in range(len(values), 200))
                self.assertLessEqual(omitted, 1e-12)

    def test_invalid_poisson_rate_or_unbounded_cutoff_rejected(self):
        for rate in (True, -1, 16, float("nan"), float("inf"), "1"):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                _poisson(rate)
        for cutoff in (True, -1, 1.5, 257):
            with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                _poisson(1, maximum=cutoff)


if __name__ == "__main__":
    unittest.main()
