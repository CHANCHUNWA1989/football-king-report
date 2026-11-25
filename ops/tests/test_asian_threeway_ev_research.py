"""Adversarial regression tests for Asian quarter-line EV and HOLD separation."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_threeway_ev_research import assess
from asian_handicap_research import grade


class AsianThreeWayEVResearchTests(unittest.TestCase):
    def test_troyes_recap_won_but_unverified_price_is_hold(self):
        self.assertEqual(grade(3, 1, "HOME", -.25), "FULL_WIN")
        row = assess([.45, .285, .265], side="HOME", handicap=-.25)
        self.assertEqual(row["status"], "HOLD")
        self.assertEqual(row["reason"], "NO_OBSERVED_DECIMAL_PRICE")
        self.assertIsNone(row["nominal_ev_per_unit_claimed_price"])
        self.assertEqual(row["formal_bet_count"], 0)
        self.assertFalse(row["positive_expected_value_verified"])

    def test_exact_minus_quarter_breakeven_accounts_for_half_loss_draw(self):
        row = assess([.45, .285, .265], side="HOME", handicap=-.25,
                     decimal_odds=1.943)
        self.assertAlmostEqual(
            row["break_even_win_probability_conditional_on_claimed_draw"],
            (1 - .5 * .285) / 1.943, places=7)
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"],
                               .45 * 1.943 + .5 * .285 - 1, places=7)
        self.assertEqual(row["reason"], "NO_CONSERVATIVE_PROBABILITY_BOUNDS")

    def test_positive_nominal_ev_below_three_percent_buffer_holds(self):
        p = [.45, .285, .265]
        row = assess(p, side="HOME", handicap=-.25, decimal_odds=1.943,
                     lower_bounds_home_draw_away=p, quote_age_seconds=30)
        self.assertGreater(row["nominal_ev_per_unit_claimed_price"], 0)
        self.assertEqual(row["reason"], "INSUFFICIENT_CONSERVATIVE_EV")
        self.assertFalse(row["research_value_screen_pass"])

    def test_uncertain_lower_bound_blocks_naive_winner_optimism(self):
        row = assess([.49, .285, .225], side="HOME", handicap=-.25,
                     decimal_odds=1.943,
                     lower_bounds_home_draw_away=[.43, .26, .20],
                     quote_age_seconds=10)
        self.assertGreater(row["nominal_ev_per_unit_claimed_price"], 0)
        self.assertLess(row["conservative_ev_lower_bound_if_claims_valid"], 0)
        self.assertEqual(row["status"], "HOLD")

    def test_research_math_pass_never_authenticates_evidence(self):
        row = assess([.70, .20, .10], side="HOME", handicap=-.25,
                     decimal_odds=1.90,
                     lower_bounds_home_draw_away=[.65, .15, .05],
                     quote_age_seconds=20)
        self.assertTrue(row["research_value_screen_pass"])
        self.assertEqual(row["status"], "RESEARCH_ONLY")
        self.assertFalse(row["positive_expected_value_verified"])
        self.assertFalse(row["price_executable_authenticated"])
        self.assertFalse(row["calibration_lower_bounds_independently_authenticated"])
        self.assertFalse(row["can_enter_formal_settlement_ledger"])
        self.assertEqual(row["production_recommendations"], "DISABLED")
        self.assertIsNone(row["recommended_stake"])

    def test_plus_quarter_draw_is_half_win_not_push(self):
        row = assess([.25, .50, .25], side="HOME", handicap=.25,
                     decimal_odds=2.0)
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"], .25)
        self.assertEqual(row["status"], "HOLD")

    def test_zero_draw_is_push_and_away_side_selects_away_win(self):
        row = assess([.5, .5, 0], side="HOME", handicap=0,
                     decimal_odds=2.0)
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"], .5)
        away = assess([.2, .3, .5], side="AWAY", handicap=-.25,
                      decimal_odds=2.0)
        self.assertAlmostEqual(away["nominal_ev_per_unit_claimed_price"],
                               .5 * 1 - .3 * .5 - .2, places=7)

    def test_never_infer_margin_from_1x2_for_three_quarter_goal_line(self):
        for line in (-.75, .75, -1.0, 1.25):
            with self.subTest(line=line):
                row = assess([.9, .05, .05], side="HOME",
                             handicap=line, decimal_odds=2)
                self.assertEqual(row["reason"], "NEEDS_FULL_SCORE_MARGIN_DISTRIBUTION")
                self.assertIsNone(row["nominal_ev_per_unit_claimed_price"])

    def test_no_quote_freshness_claim_no_research_screen(self):
        row = assess([.7, .2, .1], side="HOME", handicap=-.25,
                     decimal_odds=1.9,
                     lower_bounds_home_draw_away=[.65, .15, .05])
        self.assertEqual(row["reason"], "MISSING_OR_STALE_CLAIMED_QUOTE")
        row = assess([.7, .2, .1], side="HOME", handicap=-.25,
                     decimal_odds=1.9, quote_age_seconds=121,
                     lower_bounds_home_draw_away=[.65, .15, .05])
        self.assertEqual(row["status"], "HOLD")

    def test_bad_inputs_fail_closed_including_bool_nan_and_optimistic_lower(self):
        cases = [
            ([True, 0, 0], "HOME", -.25, 1.9, None),
            ([.5, .5, .5], "HOME", -.25, 1.9, None),
            ([float("nan"), .5, .5], "HOME", -.25, 1.9, None),
            ([.6, .2, .2], "DRAW", -.25, 1.9, None),
            ([.6, .2, .2], "HOME", True, 1.9, None),
            ([.6, .2, .2], "HOME", -.25, True, None),
            ([.6, .2, .2], "HOME", -.25, float("inf"), None),
            ([.6, .2, .2], "HOME", -.25, 1.9, [.8, .1, .1]),
            ([.6, .2, .2], "HOME", -.25, 1.9, [True, .1, .1]),
        ]
        for p, side, line, price, lower in cases:
            with self.subTest(p=p, side=side, line=line, price=price):
                row = assess(p, side=side, handicap=line,
                             decimal_odds=price,
                             lower_bounds_home_draw_away=lower)
                self.assertEqual(row["status"], "HOLD")
                self.assertFalse(row["research_value_screen_pass"])

    def test_price_floor_applies_even_when_algebra_positive(self):
        row = assess([.9, .05, .05], side="HOME", handicap=-.25,
                     decimal_odds=1.79,
                     lower_bounds_home_draw_away=[.85, .02, .03],
                     quote_age_seconds=10)
        self.assertEqual(row["reason"], "ODDS_BELOW_MINIMUM")


if __name__ == "__main__":
    unittest.main()
