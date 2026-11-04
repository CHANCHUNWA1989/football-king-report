"""Property and regression tests for PR-03 unified, hypothetical FT markets."""
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from point_in_time_store import build_cut
from unified_score_distribution_vnext import (
    grade_asian_handicap, grade_asian_total, market_grades,
    quarter_units, research_prematch, score_matrix, validate_matrix, win_draw_loss
)


def context():
    row = {
        "evidence_id": "fixture-1", "fixture_id": "ucl-research-case",
        "kind": "fixture", "source": "unit-fixture-source",
        "source_group": "synthetic-group", "source_event_id": "source-match-001",
        "source_updated_utc": "2026-11-03T19:01:00Z",
        "captured_utc": "2026-11-03T19:01:01Z",
        "received_utc": "2026-11-03T19:01:02Z",
        "available_utc": "2026-11-03T19:01:03Z",
        "raw_sha256": "a" * 64,
    }
    cut = build_cut([row], fixture_id="ucl-research-case",
                    kickoff_utc="2026-11-03T20:00:00Z",
                    decision_utc="2026-11-03T19:30:00Z", phase="PREMATCH")
    forecast = {
        "fixture_id": "ucl-research-case", "model_id": "poisson-unvalidated-vnext",
        "forecast_utc": "2026-11-03T19:40:00Z",
        "kickoff_utc": "2026-11-03T20:00:00Z",
        "expected_home_goals": 1.6, "expected_away_goals": 0.9,
        "cut_input_sha256": cut["input_sha256"],
        "production_recommendations": "DISABLED",
    }
    return forecast, cut


def report(forecast=None, cut=None, pin=None, **kwargs):
    a, b = context()
    a = forecast if forecast is not None else a
    b = cut if cut is not None else b
    params = {
        "externally_pinned_cut_sha256": b["input_sha256"] if pin is None else pin,
        "handicap_side": "HOME", "handicap_line": -0.75,
        "total_side": "OVER", "total_line": 2.25,
    }
    params.update(kwargs)
    return research_prematch(a, b, **params)


class UnifiedMatrixTests(unittest.TestCase):
    def test_poisson_grid_mass_and_explicit_tail_bound(self):
        grid = score_matrix(1.2, 0.8)
        self.assertLessEqual(grid["tail_mass_upper_bound"], 1e-10)
        self.assertAlmostEqual(sum(map(sum, grid["matrix"])), 1.0, places=11)

    def test_high_rates_have_bounded_nonzero_tail(self):
        grid = score_matrix(5.5, 5.5)
        self.assertLessEqual(grid["tail_mass_upper_bound"], 1e-10)
        self.assertGreater(len(grid["matrix"]), 20)

    def test_zero_rates_generate_certain_0_0(self):
        grid = score_matrix(0, 0)["matrix"]
        self.assertEqual(grid, [[1.0]])
        self.assertEqual(win_draw_loss(grid), {"HOME": 0.0, "DRAW": 1.0, "AWAY": 0.0})

    def test_bad_rates_fail_closed(self):
        for value in (True, None, float("nan"), float("inf"), -0.01, 5.50001):
            with self.subTest(rate=value), self.assertRaises(ValueError):
                score_matrix(value, 1.0)

    def test_bad_matrix_shape_and_mass_rejected(self):
        for matrix in ([], [[1], [0, 0]], [[0.25]], [[-0.1, 1.1]],
                       [[float("nan"), 1]], [[True, 0]], ((1,),), [1, 2]):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                validate_matrix(matrix)

    def test_1x2_sum_and_symmetry(self):
        for home, away in ((1.4, 1.4), (0.8, 2.3)):
            with self.subTest(home=home, away=away):
                p = win_draw_loss(score_matrix(home, away)["matrix"])
                self.assertAlmostEqual(sum(p.values()), 1.0, places=10)
                q = win_draw_loss(score_matrix(away, home)["matrix"])
                self.assertAlmostEqual(p["HOME"], q["AWAY"], places=11)
                self.assertAlmostEqual(p["DRAW"], q["DRAW"], places=11)

    def test_scoreline_matrix_has_correct_h2h(self):
        m = [[0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 1.0, 0]]
        self.assertEqual(win_draw_loss(m), {"HOME": 1.0, "DRAW": 0.0, "AWAY": 0.0})

    def test_home_minus_075_one_goal_win_is_half_win(self):
        self.assertEqual(grade_asian_handicap(3, 2, side="HOME", line=-0.75), "HALF_WIN")

    def test_home_minus_025_draw_is_half_loss(self):
        self.assertEqual(grade_asian_handicap(0, 0, side="HOME", line=-0.25), "HALF_LOSS")

    def test_home_plus_025_draw_is_half_win(self):
        self.assertEqual(grade_asian_handicap(0, 0, side="HOME", line=+0.25), "HALF_WIN")

    def test_home_minus_1_one_goal_win_is_push(self):
        self.assertEqual(grade_asian_handicap(1, 0, side="HOME", line=-1), "PUSH")

    def test_home_minus_15_one_goal_win_is_full_loss(self):
        self.assertEqual(grade_asian_handicap(1, 0, side="HOME", line=-1.5), "FULL_LOSS")

    def test_away_plus_125_loss_by_one_is_half_win(self):
        self.assertEqual(grade_asian_handicap(2, 1, side="AWAY", line=+1.25), "HALF_WIN")

    def test_away_minus_075_one_goal_win_is_half_win(self):
        self.assertEqual(grade_asian_handicap(1, 2, side="AWAY", line=-0.75), "HALF_WIN")

    def test_over_225_two_goals_is_half_loss(self):
        self.assertEqual(grade_asian_total(1, 1, side="OVER", line=2.25), "HALF_LOSS")

    def test_under_225_two_goals_is_half_win(self):
        self.assertEqual(grade_asian_total(2, 0, side="UNDER", line=2.25), "HALF_WIN")

    def test_over_275_three_goals_is_half_win(self):
        self.assertEqual(grade_asian_total(1, 2, side="OVER", line=2.75), "HALF_WIN")

    def test_under_275_three_goals_is_half_loss(self):
        self.assertEqual(grade_asian_total(1, 2, side="UNDER", line=2.75), "HALF_LOSS")

    def test_half_line_total_win_loss(self):
        self.assertEqual(grade_asian_total(1, 1, side="OVER", line=2.5), "FULL_LOSS")
        self.assertEqual(grade_asian_total(2, 1, side="OVER", line=2.5), "FULL_WIN")

    def test_zero_line_push_0_0(self):
        self.assertEqual(grade_asian_total(0, 0, side="OVER", line=0), "PUSH")

    def test_line_parsing_is_exact_no_auto_rounding(self):
        for value in (True, "NaN", float("inf"), 0.26, "0.300", -10.25):
            with self.subTest(value=value), self.assertRaises(ValueError):
                quarter_units(value, minimum=-10, maximum=10)
        self.assertEqual(quarter_units("-0.75", minimum=-10, maximum=10), -3)

    def test_negative_totals_and_wrong_sides_rejected(self):
        with self.assertRaises(ValueError):
            grade_asian_total(1, 1, side="OVER", line=-0.25)
        with self.assertRaises(ValueError):
            grade_asian_handicap(1, 0, side="OVER", line=-0.5)
        with self.assertRaises(ValueError):
            grade_asian_total(1, 1, side="HOME", line=2.5)

    def test_invalid_goals_are_not_silently_rounded(self):
        for goals in (1.5, True, -1, 66):
            with self.subTest(goals=goals), self.assertRaises(ValueError):
                grade_asian_handicap(goals, 0, side="HOME", line=0)

    def test_five_grade_market_distribution_sums_to_one(self):
        matrix = score_matrix(1.2, 1.8)["matrix"]
        for market, side, line in (("ASIAN_TOTAL", "UNDER", 2.75),
                                   ("ASIAN_TOTAL", "OVER", 3.0),
                                   ("ASIAN_HANDICAP", "HOME", -1.25),
                                   ("ASIAN_HANDICAP", "AWAY", 0.25)):
            with self.subTest(market=market, side=side):
                p = market_grades(matrix, market=market, side=side, line=line)
                self.assertAlmostEqual(sum(p.values()), 1, places=10)
                self.assertEqual(set(p), {"FULL_WIN", "HALF_WIN", "PUSH",
                                          "HALF_LOSS", "FULL_LOSS"})

    def test_opposite_spread_sides_are_complementary(self):
        matrix = score_matrix(1.6, 0.9)["matrix"]
        h = market_grades(matrix, market="ASIAN_HANDICAP", side="HOME", line=-0.75)
        a = market_grades(matrix, market="ASIAN_HANDICAP", side="AWAY", line=+0.75)
        self.assertAlmostEqual(h["FULL_WIN"], a["FULL_LOSS"], places=11)
        self.assertAlmostEqual(h["HALF_WIN"], a["HALF_LOSS"], places=11)
        self.assertAlmostEqual(h["PUSH"], a["PUSH"], places=11)

    def test_over_and_under_are_complementary(self):
        matrix = score_matrix(1.6, 0.9)["matrix"]
        over = market_grades(matrix, market="ASIAN_TOTAL", side="OVER", line=2.25)
        under = market_grades(matrix, market="ASIAN_TOTAL", side="UNDER", line=2.25)
        self.assertAlmostEqual(over["FULL_WIN"], under["FULL_LOSS"], places=11)
        self.assertAlmostEqual(over["HALF_WIN"], under["HALF_LOSS"], places=11)
        self.assertAlmostEqual(over["PUSH"], under["PUSH"], places=11)

    def test_report_uses_single_matrix_and_remains_nonbetting(self):
        r = report()
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["model_scoring_eligible"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["bookmaker_quote_authenticated"])
        self.assertEqual(r["recommended_bets"], [])
        matrix = r["score_matrix"]
        self.assertEqual(r["markets"]["h2h"], win_draw_loss(matrix))
        self.assertEqual(r["markets"]["asian_handicap"]["grades"],
                         market_grades(matrix, market="ASIAN_HANDICAP",
                                       side="HOME", line=-0.75))
        self.assertEqual(r["markets"]["asian_total"]["grades"],
                         market_grades(matrix, market="ASIAN_TOTAL",
                                       side="OVER", line=2.25))
        self.assertLessEqual(r["tail_mass_upper_bound"], 1e-10)
        self.assertNotIn("decimal_odds", str(r))
        self.assertNotIn("ev_estimate", str(r))

    def test_missing_external_pin_holds(self):
        self.assertEqual(report(pin="")["status"], "HOLD")

    def test_wrong_pinned_digest_holds(self):
        self.assertEqual(report(pin="a" * 64)["reason"],
                         "MISSING_OR_UNPINNED_EVIDENCE_CUT")

    def test_inplay_cut_cannot_supply_prematch_report(self):
        _, cut = context()
        altered = copy.deepcopy(cut)
        altered["phase"] = "INPLAY"
        self.assertEqual(report(cut=altered)["reason"], "ONLY_PREMATCH_CUTS_SUPPORTED")

    def test_forecast_after_kickoff_rejected(self):
        f, c = context()
        f["forecast_utc"] = "2026-11-03T20:01:00Z"
        self.assertEqual(report(forecast=f, cut=c)["reason"],
                         "FORECAST_NOT_POINT_IN_TIME_PREMATCH")

    def test_forecast_before_cut_rejected(self):
        f, c = context()
        f["forecast_utc"] = "2026-11-03T19:20:00Z"
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_cut_and_forecast_fixture_mismatch_rejected(self):
        f, c = context()
        f["fixture_id"] = "another-match"
        self.assertEqual(report(forecast=f, cut=c)["reason"],
                         "EVIDENCE_CUT_IDENTITY_OR_TRUST_CONFLICT")

    def test_injected_result_field_is_not_accepted(self):
        f, c = context()
        f["full_time_result"] = "H"
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_research_quote_field_is_not_accepted(self):
        f, c = context()
        f["bookmaker_odds"] = 2.8
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_untrusted_cut_claims_are_rejected(self):
        f, c = context()
        c["source_authenticated"] = True
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_non_disabled_forecast_rejected(self):
        f, c = context()
        f["production_recommendations"] = "ENABLED"
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_invalid_rate_holds_not_partial_report(self):
        f, c = context()
        f["expected_home_goals"] = float("nan")
        self.assertEqual(report(forecast=f, cut=c)["status"], "HOLD")

    def test_invalid_line_holds_not_partial_report(self):
        self.assertEqual(report(total_line=2.3)["status"], "HOLD")

    def test_report_is_deterministic_for_same_sealed_inputs(self):
        self.assertEqual(report(), report())


if __name__ == "__main__":
    unittest.main()
