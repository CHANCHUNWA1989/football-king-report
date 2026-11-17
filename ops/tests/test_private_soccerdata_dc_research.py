import math
import unittest
from unittest.mock import patch
from ops import private_soccerdata_dc_research as dc_core
from ops.private_soccerdata_dc_research import evaluate_dixon_coles_correction, _estimate_rho, _tau
from ops.private_soccerdata_team_poisson import evaluate_team_poisson
from ops.tests.test_private_soccerdata_team_poisson import skewed_records


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
        self.assertEqual(report["model"], "approximate_low_score_dixon_coles_conditional_rho_v5")
        self.assertEqual(report.get("rho_likelihood_basis"), "FITTED_TRAINING_MATCH_RATES")
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

    def test_correction_uses_target_rates_instead_of_league_average_mass(self):
        records = skewed_records()
        baseline = evaluate_team_poisson(records, min_train=5, test_days=1)
        report = evaluate_dixon_coles_correction(records, min_train=5, test_days=1)
        prediction = report["predictions"][0]
        self.assertEqual(prediction["training_only_rho"], -.1)
        # Independent closed-form DC mass transfer at the hand-derived rates.
        home_rate, away_rate = 20 / 7, 10 / 21
        shift = home_rate * away_rate * -.1 * math.exp(-home_rate - away_rate)
        original = baseline["predictions"][0]["probabilities"]
        expected = {"H": original["H"] + shift, "D": original["D"] - 2 * shift,
                    "A": original["A"] + shift}
        for outcome in ("H", "D", "A"):
            self.assertAlmostEqual(prediction["probabilities"][outcome], expected[outcome], places=10)

    def test_prediction_rate_constraint_excludes_invalid_target_tau(self):
        records = [row(i, "2026-01-01", 20, 0) for i in range(1, 7)]
        records += [{**row(i, "2026-01-01", 0, 0), "home_team": "C", "away_team": "D"}
                    for i in range(7, 27)]
        records.append(row(27, "2026-01-02", 1, 0))
        try:
            report = evaluate_dixon_coles_correction(records, min_train=26, test_days=1)
        except ValueError as error:
            self.fail(f"Valid high-strength fixture was rejected: {error}")
        prediction = report["predictions"][0]
        # The fitted target home rate reaches the unchanged cap15. League-only
        # rho=-.1 would make target tau(0,1)=-.5; rho=-.06 remains admissible.
        self.assertEqual(prediction["training_only_rho"], -.06)
        self.assertIn("expected_home_goals", prediction)
        for h, a in ((0, 0), (0, 1), (1, 0), (1, 1)):
            self.assertGreater(_tau(h, a, prediction["expected_home_goals"],
                                    prediction["expected_away_goals"], -.06), 0)

    def test_target_outcome_does_not_change_rate_mass_or_rho_forecast(self):
        records = skewed_records()
        original = [dict(r) for r in records]
        before = evaluate_dixon_coles_correction(records, min_train=5, test_days=1)
        changed = [dict(r) for r in records]
        changed[-1].update(home_goals=0, away_goals=30, outcome="A")
        after = evaluate_dixon_coles_correction(changed, min_train=5, test_days=1)
        for field in ("probabilities", "training_only_rho", "expected_home_goals",
                      "expected_away_goals", "low_score_probabilities"):
            self.assertEqual(before["predictions"][0][field], after["predictions"][0][field])
        self.assertEqual(records, original)

    def test_conditional_likelihood_uses_each_training_fixture_rate(self):
        training = [{"home_goals": 0, "away_goals": 0},
                    {"home_goals": 0, "away_goals": 1}]
        # With uniform rates4/4, the grid maximizer is negative. The actual
        # conditional likelihood is (1-.01*rho)*(1+5*rho), increasing on grid.
        self.assertLess(_estimate_rho(training, 4, 4, prediction_rates=(1, 1)), 0)
        try:
            selected = _estimate_rho(training, 4, 4, prediction_rates=(1, 1),
                                     training_rates=[(.1, .1), (5, 1)])
        except TypeError as error:
            self.fail(f"Per-fixture training rates are not supported: {error}")
        self.assertEqual(selected, .1)

    def test_public_fit_profiles_prior_matches_once_per_fold(self):
        self.assertTrue(hasattr(dc_core, "_rho_scores"))
        records = skewed_records() + [row(7, "2026-01-03", 0, 0)]
        with patch.object(dc_core, "_rho_scores", wraps=dc_core._rho_scores) as profile:
            report = evaluate_dixon_coles_correction(records, min_train=5, test_days=7)
        self.assertEqual(report["prediction_count"], 2)
        self.assertEqual(profile.call_count, report["fold_count"])
        training, rates = profile.call_args.args
        self.assertEqual([r["source_index"] for r in training], ["1", "2", "3", "4", "5"])
        self.assertEqual(len(training), len(rates))
        self.assertAlmostEqual(rates[0][0], 20 / 7, places=14)
        self.assertAlmostEqual(rates[0][1], 10 / 21, places=14)
        self.assertAlmostEqual(rates[-1][0], 10 / 9, places=14)
        self.assertAlmostEqual(rates[-1][1], 5 / 9, places=14)
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["model_promoted"])

    def test_misaligned_or_invalid_training_rate_profiles_rejected(self):
        training = [{"home_goals": 0, "away_goals": 0},
                    {"home_goals": 0, "away_goals": 1}]
        for rates in ([(1, 1)], [(True, 1), (1, 1)], [(float("nan"), 1), (1, 1)],
                      [(-1, 1), (1, 1)], [(1,), (1, 1)]):
            with self.subTest(rates=rates):
                try:
                    with self.assertRaises(ValueError):
                        _estimate_rho(training, 1, 1, training_rates=rates)
                except TypeError as error:
                    self.fail(f"Training-rate profile validation missing: {error}")


if __name__ == "__main__":
    unittest.main()
