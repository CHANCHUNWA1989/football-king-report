"""Synthetic sealed-rate policy tests, not independent market/outcome evidence."""
import copy
import importlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.tests.test_case_fourway_scoring import paired_fixture
from asian_handicap_research import TYPES, grade as canonical_handicap_grade
from model_ab import candidate as b_candidate
from model_market_challenger import candidate as c_candidate
from shadow_forecast import poisson_1x2


def goal_fixture(home_rate=2.0, away_rate=1.0):
    pair = paired_fixture()
    pair["model"] = poisson_1x2(home_rate, away_rate)
    pair["ab"] = b_candidate(pair["model"])
    pair["c"] = c_candidate(pair["model"], pair["market"])
    forecast = {field: pair[field] for field in (
        "league", "home", "away", "kickoff_utc", "prediction_utc", "production_recommendations")}
    forecast.update(event_id=pair["forecast_event_id"],
                    model="poisson-shrinkage-unvalidated-v4.1",
                    training_games=54, training_cutoff_local_day="2026-10-20",
                    training_observations_sha256="a" * 64,
                    expected_home_goals=home_rate, expected_away_goals=away_rate,
                    p_home=pair["model"][0], p_draw=pair["model"][1], p_away=pair["model"][2],
                    calibrated=False, verified_market_odds=False)
    return pair, forecast


class CaseGoalMarketScoringTests(unittest.TestCase):
    def function(self):
        self.assertIsNotNone(importlib.util.find_spec("ops.case_goal_market_scoring"),
                             "No original-case sealed-rate goal-market scoring boundary exists")
        return importlib.import_module("ops.case_goal_market_scoring").score_goal_markets

    def report(self, goals=None, rates=(2.0, 1.0)):
        pair, forecast = goal_fixture(*rates)
        return self.function()(pair, forecast, [2, 1] if goals is None else goals)

    def assert_held(self, report):
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertIs(report["candidate_only"], True)
        self.assertIs(report["derived_reconstruction"], True)
        self.assertIs(report["distribution_sealed_pre_match"], False)
        self.assertIs(type(report["certified_case_count"]), int)
        self.assertEqual(report["certified_case_count"], 0)
        for flag in ("independently_verified", "eligible_for_model_scoring",
                     "eligible_for_betting_promotion", "results_independently_verified",
                     "offered_handicap_line_authenticated", "offered_totals_line_authenticated",
                     "offered_decimal_odds_authenticated", "probability_calibration_verified",
                     "positive_expected_value_verified", "B_C_market_goal_distributions_available"):
            self.assertIs(report[flag], False, flag)

    def test_positive_fixed_full_grid_scores_all_supported_quarter_lines(self):
        pair, forecast = goal_fixture()
        report = self.function()(pair, forecast, [2, 1])
        self.assert_held(report)
        self.assertEqual(report["case_id"], pair["case_id"])
        self.assertEqual(report["forecast_event_id"], forecast["event_id"])
        self.assertEqual(report["score_ft_candidate"], [2, 1])
        self.assertEqual(len(report["asian_handicap"]), 82)
        self.assertEqual(len(report["totals"]), 82)
        self.assertEqual(report["market_projection_count"], 164)
        self.assertEqual({(row["side"], row["line"]) for row in report["asian_handicap"]},
                         {(side, units / 4) for side in ("HOME", "AWAY") for units in range(-20, 21)})
        self.assertEqual({(row["side"], row["line"]) for row in report["totals"]},
                         {(side, units / 4) for side in ("OVER", "UNDER") for units in range(41)})
        for row in report["asian_handicap"] + report["totals"]:
            probs = row["grade_probabilities"]
            self.assertEqual(set(probs), set(TYPES))
            self.assertAlmostEqual(sum(probs.values()), 1, places=12)
            self.assertTrue(all(type(value) is float and math.isfinite(value) and 0 <= value <= 1
                                for value in probs.values()))
            actual = row["observed_grade_candidate"]
            self.assertIn(actual, TYPES)
            self.assertAlmostEqual(row["log_loss"], -math.log(max(probs[actual], 1e-15)), places=12)
            self.assertAlmostEqual(row["brier"], sum((value - int(grade == actual)) ** 2
                                                    for grade, value in probs.items()), places=12)
        diagnostics = report["distribution_diagnostics"]
        self.assertEqual(diagnostics["sealed_expected_home_goals"], 2.0)
        self.assertEqual(diagnostics["sealed_expected_away_goals"], 1.0)
        self.assertEqual(diagnostics["original_A_probabilities"], pair["model"])
        self.assertEqual(diagnostics["grid_max_goals_each"], 24)
        self.assertTrue(diagnostics["probabilities_conditioned_on_truncation"])
        self.assertLess(diagnostics["omitted_joint_mass_upper_bound"], 1e-8)
        self.assertLess(len(json.dumps(report)), 100000)

    def test_btts_matches_hand_calculation_and_preserves_source_inputs(self):
        # Independent rates log(2) give P(H>0)=P(A>0)=1/2, hence BTTS=1/4.
        pair, forecast = goal_fixture(math.log(2), math.log(2))
        original = copy.deepcopy((pair, forecast))
        report = self.function()(pair, forecast, [1, 1])
        self.assertIn("both_teams_to_score", report)
        btts = report["both_teams_to_score"]
        self.assertAlmostEqual(btts["probabilities"]["YES"], .25, places=12)
        self.assertAlmostEqual(btts["probabilities"]["NO"], .75, places=12)
        self.assertEqual(btts["observed_outcome_candidate"], "YES")
        self.assertAlmostEqual(btts["binary_brier"], .5625, places=12)
        self.assertAlmostEqual(btts["log_loss"], 1.3862943611198906, places=12)
        self.assertEqual(report["market_projection_count"], 164)
        self.assertEqual(report["market_projection_count_basis"], "AH_TOTALS_FIXED_SCENARIOS")
        self.assertEqual((pair, forecast), original)
        self.assert_held(report)
        self.assertEqual(btts["status"], "HOLD")
        self.assertEqual(btts["production_recommendations"], "DISABLED")
        for flag in ("forecast_sealed_pre_match", "offered_market_authenticated",
                     "calibration_verified", "results_independently_verified", "positive_ev_verified"):
            self.assertIs(btts[flag], False)
        self.assertNotIn("ev", btts)
        self.assertNotIn("decimal_odds", btts)

    def test_btts_probabilities_do_not_depend_on_candidate_result(self):
        previous = None
        for score, outcome, brier in (([0, 0], "NO", .0625), ([0, 2], "NO", .0625),
                                      ([2, 0], "NO", .0625), ([1, 1], "YES", .5625),
                                      ([30, 30], "YES", .5625)):
            with self.subTest(score=score):
                report = self.report(score, rates=(math.log(2), math.log(2)))
                self.assertIn("both_teams_to_score", report)
                btts = report["both_teams_to_score"]
                if previous is not None:
                    self.assertEqual(btts["probabilities"], previous)
                previous = btts["probabilities"]
                self.assertEqual(btts["observed_outcome_candidate"], outcome)
                self.assertAlmostEqual(btts["binary_brier"], brier, places=12)
                if outcome == "NO":
                    self.assertAlmostEqual(btts["log_loss"], .2876820724517809, places=12)

    def test_btts_extreme_rates_preserve_mass_and_report_grid_approximation(self):
        for home_rate, away_rate in ((.1, .1), (5.5, 5.5), (.1, 5.5), (5.5, .1)):
            with self.subTest(rates=(home_rate, away_rate)):
                report = self.report(rates=(home_rate, away_rate))
                self.assertIn("both_teams_to_score", report)
                probabilities = report["both_teams_to_score"]["probabilities"]
                expected = (1 - math.exp(-home_rate)) * (1 - math.exp(-away_rate))
                bound = report["distribution_diagnostics"]["omitted_joint_mass_upper_bound"]
                self.assertLessEqual(abs(probabilities["YES"] - expected), bound)
                self.assertAlmostEqual(sum(probabilities.values()), 1, places=12)
                self.assertTrue(all(type(p) is float and math.isfinite(p) and 0 <= p <= 1
                                    for p in probabilities.values()))

    def test_correct_score_top_five_preserve_ties_and_original_probability_mass(self):
        pair, forecast = goal_fixture(2.0, 1.0)
        original = copy.deepcopy((pair, forecast))
        report = self.function()(pair, forecast, [2, 1])
        self.assertIn("correct_score_diagnostic", report)
        scores = report["correct_score_diagnostic"]
        self.assertEqual(scores["top_k"], 5)
        top = scores["top_scorelines"]
        self.assertEqual([(r["home_goals"], r["away_goals"]) for r in top],
                         [(1, 0), (1, 1), (2, 0), (2, 1), (3, 0)])
        # Four modes each have 2*exp(-3); the fifth has (4/3)*exp(-3).
        for row in top[:4]:
            self.assertAlmostEqual(row["probability"], .09957413673572789, places=12)
        self.assertAlmostEqual(top[4]["probability"], .06638275782381859, places=12)
        self.assertAlmostEqual(scores["top_scorelines_probability_mass"], .4646793047667301, places=12)
        self.assertAlmostEqual(scores["other_in_grid_probability_mass"], .5353206952332699, places=12)
        self.assertAlmostEqual(scores["candidate_score_probability"], .09957413673572789, places=12)
        self.assertAlmostEqual(scores["candidate_score_log_loss"], 2.3068528194400546, places=12)
        self.assertIs(scores["candidate_score_in_grid"], True)
        self.assertEqual(scores["status"], "HOLD")
        self.assertEqual(scores["production_recommendations"], "DISABLED")
        for flag in ("forecast_sealed_pre_match", "offered_market_authenticated",
                     "calibration_verified", "results_independently_verified", "positive_ev_verified"):
            self.assertIs(scores[flag], False)
        self.assertEqual(report["market_projection_count"], 164)
        self.assertEqual((pair, forecast), original)

    def test_correct_score_ranking_does_not_depend_on_candidate_outcome(self):
        first = self.report([0, 0])
        second = self.report([30, 30])
        self.assertIn("correct_score_diagnostic", first)
        self.assertIn("correct_score_diagnostic", second)
        a, b = first["correct_score_diagnostic"], second["correct_score_diagnostic"]
        self.assertEqual(a["top_scorelines"], b["top_scorelines"])
        self.assertEqual(a["top_scorelines_probability_mass"], b["top_scorelines_probability_mass"])
        self.assertEqual(a["other_in_grid_probability_mass"], b["other_in_grid_probability_mass"])
        self.assertIs(b["candidate_score_in_grid"], False)
        self.assertIsNone(b["candidate_score_probability"])
        self.assertIsNone(b["candidate_score_log_loss"])
        self.assertEqual(b["candidate_score_reason"], "OUTSIDE_RETAINED_SCORE_GRID")

    def test_correct_score_grid_boundary_and_extreme_rates_are_explicit(self):
        for rates in ((.1, .1), (5.5, 5.5), (.1, 5.5)):
            for outcome in ([24, 24], [25, 0], [0, 25]):
                with self.subTest(rates=rates, outcome=outcome):
                    report = self.report(outcome, rates=rates)
                    self.assertIn("correct_score_diagnostic", report)
                    scores = report["correct_score_diagnostic"]
                    self.assertIs(scores["probabilities_conditioned_on_truncation"], True)
                    self.assertTrue(all(0 <= row["home_goals"] <= 24 and 0 <= row["away_goals"] <= 24
                                        and math.isfinite(row["probability"]) and 0 <= row["probability"] <= 1
                                        for row in scores["top_scorelines"]))
                    self.assertGreater(scores["top_scorelines_probability_mass"], 0)
                    self.assertLess(scores["top_scorelines_probability_mass"], 1)
                    self.assertAlmostEqual(scores["top_scorelines_probability_mass"]
                                           + scores["other_in_grid_probability_mass"], 1, places=12)
                    if outcome == [24, 24]:
                        self.assertIs(scores["candidate_score_in_grid"], True)
                        self.assertGreater(scores["candidate_score_probability"], 0)
                        self.assertTrue(math.isfinite(scores["candidate_score_log_loss"]))
                        self.assertAlmostEqual(scores["candidate_score_log_loss"],
                                               -math.log(scores["candidate_score_probability"]), places=12)
                    else:
                        self.assertIs(scores["candidate_score_in_grid"], False)
                        self.assertIsNone(scores["candidate_score_probability"])
                        self.assertIsNone(scores["candidate_score_log_loss"])

    def test_quarter_and_integer_lines_grade_exact_candidate_scores(self):
        report = self.report()
        ah = {(row["side"], row["line"]): row for row in report["asian_handicap"]}
        totals = {(row["side"], row["line"]): row for row in report["totals"]}
        for key, expected in ((("HOME", -.75), "HALF_WIN"), (("HOME", -1), "PUSH"),
                              (("HOME", -1.25), "HALF_LOSS"), (("AWAY", .75), "HALF_LOSS")):
            self.assertEqual(ah[key]["observed_grade_candidate"], expected)
        for key, expected in ((("OVER", 2.75), "HALF_WIN"), (("UNDER", 2.75), "HALF_LOSS"),
                              (("OVER", 3), "PUSH"), (("OVER", 3.25), "HALF_LOSS"),
                              (("UNDER", 3.25), "HALF_WIN")):
            self.assertEqual(totals[key]["observed_grade_candidate"], expected)
        for row in report["asian_handicap"]:
            self.assertEqual(row["observed_grade_candidate"], canonical_handicap_grade(
                2, 1, row["side"], row["line"]))

    def test_opposite_wagers_reverse_all_grades_and_probability_mass(self):
        report = self.report()
        reverse = dict(zip(TYPES, reversed(TYPES)))
        ah = {(row["side"], row["line"]): row for row in report["asian_handicap"]}
        totals = {(row["side"], row["line"]): row for row in report["totals"]}
        for (side, line), row in ah.items():
            other = ah[("AWAY" if side == "HOME" else "HOME", -line)]
            self.assertEqual(other["observed_grade_candidate"], reverse[row["observed_grade_candidate"]])
            for grade, probability in row["grade_probabilities"].items():
                self.assertAlmostEqual(other["grade_probabilities"][reverse[grade]], probability, places=12)
        for (side, line), row in totals.items():
            other = totals[("UNDER" if side == "OVER" else "OVER", line)]
            self.assertEqual(other["observed_grade_candidate"], reverse[row["observed_grade_candidate"]])
            for grade, probability in row["grade_probabilities"].items():
                self.assertAlmostEqual(other["grade_probabilities"][reverse[grade]], probability, places=12)

    def test_all_valid_controlled_score_bounds_and_totals_endpoints(self):
        for goals in ([0, 0], [0, 30], [30, 0], [30, 30]):
            with self.subTest(goals=goals):
                report = self.report(goals)
                self.assert_held(report)
                totals = {(row["side"], row["line"]): row for row in report["totals"]}
                self.assertEqual(totals[("OVER", 0)]["observed_grade_candidate"],
                                 "PUSH" if sum(goals) == 0 else "FULL_WIN")
                self.assertEqual(totals[("UNDER", 10)]["observed_grade_candidate"],
                                 "FULL_WIN" if sum(goals) < 10 else "FULL_LOSS")

    def test_grid_is_fixed_and_never_selected_using_observed_outcome(self):
        first, second = self.report([0, 0]), self.report([30, 30])
        for family in ("asian_handicap", "totals"):
            self.assertEqual([(row["side"], row["line"], row["grade_probabilities"]) for row in first[family]],
                             [(row["side"], row["line"], row["grade_probabilities"]) for row in second[family]])

    def test_rate_extremes_preserve_mass_and_explicit_truncation(self):
        for rates in ((.1, .1), (5.5, 5.5), (.1, 5.5)):
            with self.subTest(rates=rates):
                report = self.report(rates=rates)
                diagnostics = report["distribution_diagnostics"]
                self.assertGreater(diagnostics["retained_joint_mass_before_conditioning"], .99999)
                self.assertLessEqual(diagnostics["retained_joint_mass_before_conditioning"], 1)
                self.assertGreater(diagnostics["omitted_joint_mass_upper_bound"], 0)
                self.assertLess(diagnostics["omitted_joint_mass_upper_bound"], 1e-8)
                for row in report["asian_handicap"] + report["totals"]:
                    self.assertAlmostEqual(sum(row["grade_probabilities"].values()), 1, places=12)

    def test_missing_bool_nonfinite_or_out_of_policy_rates_are_rejected(self):
        for field in ("expected_home_goals", "expected_away_goals"):
            for value in (None, True, False, float("nan"), float("inf"), 0, .09, 5.6, "2.0", 10**400):
                with self.subTest(field=field, value=repr(value)):
                    pair, forecast = goal_fixture()
                    forecast[field] = value
                    with self.assertRaisesRegex(ValueError, "^INVALID_SEALED_GOAL_RATES$"):
                        self.function()(pair, forecast, [2, 1])
            pair, forecast = goal_fixture()
            forecast.pop(field)
            with self.assertRaises(ValueError):
                self.function()(pair, forecast, [2, 1])

    def test_forecast_identity_or_probability_mismatch_is_rejected(self):
        changes = {"event_id": "openligadb:999", "league": "epl", "home": "other-home",
                   "away": "other-away", "kickoff_utc": "2026-10-23T18:31:00Z",
                   "prediction_utc": "2026-10-21T02:09:00Z", "p_home": .3,
                   "p_draw": True, "p_away": float("nan")}
        for field, value in changes.items():
            with self.subTest(field=field):
                pair, forecast = goal_fixture()
                forecast[field] = value
                with self.assertRaisesRegex(ValueError, "^GOAL_FORECAST_IDENTITY_MISMATCH$"):
                    self.function()(pair, forecast, [2, 1])
        pair, forecast = goal_fixture()
        forecast.update(forecast_event_id="openligadb:999", source_fixture_identity={
            "provider": "OpenLigaDB", "match_id": "999"},
            source_fixture_identity_status="UNAUTHENTICATED", independently_verified=False,
            eligible_for_model_scoring=False)
        with self.assertRaises(ValueError):
            self.function()(pair, forecast, [2, 1])

    def test_training_metadata_and_source_model_must_be_original_and_pre_match(self):
        for field, value in (("model", "later-refitted-model"), ("training_games", True),
                             ("training_games", 29), ("training_observations_sha256", "not-a-hash"),
                             ("training_cutoff_local_day", "2026-10-21"),
                             ("training_cutoff_local_day", "not-a-day")):
            with self.subTest(field=field):
                pair, forecast = goal_fixture()
                forecast[field] = value
                with self.assertRaisesRegex(ValueError, "^INVALID_SEALED_GOAL_MODEL_METADATA$"):
                    self.function()(pair, forecast, [2, 1])

    def test_arbitrary_different_rates_cannot_be_attached_to_original_probabilities(self):
        pair, forecast = goal_fixture()
        forecast["expected_home_goals"] = .1
        with self.assertRaisesRegex(ValueError, "^SEALED_RATE_PROBABILITY_CONFLICT$"):
            self.function()(pair, forecast, [2, 1])

    def test_sealed_rate_rounding_drift_is_reported_without_replacing_A(self):
        pair, forecast = goal_fixture(2.54946, .97344)
        original = [.7144087, .1628881, .1227032]
        pair["model"] = original
        pair.update(ab=b_candidate(original), c=c_candidate(original, pair["market"]))
        forecast.update(p_home=original[0], p_draw=original[1], p_away=original[2])
        report = self.function()(pair, forecast, [2, 3])
        diagnostics = report["distribution_diagnostics"]
        self.assertEqual(diagnostics["original_A_probabilities"], original)
        self.assertNotEqual(diagnostics["original_12_goal_grid_replay"], original)
        self.assertGreater(diagnostics["max_original_rate_replay_gap"], 0)
        self.assertLess(diagnostics["max_original_rate_replay_gap"], diagnostics["rate_rounding_consistency_tolerance"])
        self.assertEqual(pair["model"], original)

    def test_promotion_claims_or_result_bearing_inputs_are_rejected(self):
        for field, value in (("production_recommendations", "ENABLED"), ("calibrated", True),
                             ("verified_market_odds", True), ("result", "home"),
                             ("historical_outcome", 0), ("score_ft", [2, 1]),
                             ("independently_verified", True), ("eligible_for_model_scoring", True)):
            with self.subTest(field=field):
                pair, forecast = goal_fixture()
                forecast[field] = value
                with self.assertRaisesRegex(ValueError, "^UNSAFE_GOAL_FORECAST$"):
                    self.function()(pair, forecast, [2, 1])
        pair, forecast = goal_fixture()
        pair["eligible_for_model_scoring"] = True
        with self.assertRaises(ValueError):
            self.function()(pair, forecast, [2, 1])

    def test_inputs_are_not_mutated_and_no_other_model_distributions_appear(self):
        pair, forecast = goal_fixture()
        original = copy.deepcopy((pair, forecast))
        report = self.function()(pair, forecast, [2, 1])
        self.assertEqual((pair, forecast), original)
        self.assertNotIn("B", report)
        self.assertNotIn("C", report)
        self.assertNotIn("market", report)
        self.assert_held(report)

    def test_non_object_forecast_is_sanitized(self):
        pair, _ = goal_fixture()
        for forecast in (None, [], "private-sensitive-forecast", False):
            with self.subTest(forecast=repr(forecast)):
                with self.assertRaisesRegex(ValueError, "^INVALID_GOAL_FORECAST$"):
                    self.function()(pair, forecast, [2, 1])


if __name__ == "__main__":
    unittest.main()
