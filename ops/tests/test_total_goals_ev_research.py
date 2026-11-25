"""Exact 5-grade Asian total-goal research EV and fail-closed controls."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from total_goals_ev_research import assess, _grade, _line_units


class TotalGoalsEVResearchTests(unittest.TestCase):
    def test_over_275_three_goals_half_wins_and_binary_formula_is_wrong(self):
        row = assess({"2": .4, "3": .6}, side="OVER", line=2.75,
                     decimal_odds=2)
        self.assertEqual(row["status"], "HOLD")
        self.assertEqual(row["reason"], "NO_CONSERVATIVE_TOTAL_LOWER_BOUNDS")
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"], -.1)
        self.assertAlmostEqual(row["five_grade_probabilities_unverified"]["HALF_WIN"], .6)
        self.assertAlmostEqual(row["five_grade_probabilities_unverified"]["FULL_LOSS"], .4)
        self.assertFalse(row["positive_expected_value_verified"])
        # The incorrect binary 0.6 * 2 - 1 would falsely claim +0.20.
        self.assertGreater(.6 * 2 - 1, 0)

    def test_under_275_three_goals_half_loses(self):
        row = assess({2: .3, 3: .7}, side="UNDER", line=2.75,
                     decimal_odds=2)
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"], -.05)
        self.assertEqual(row["five_grade_probabilities_unverified"]["HALF_LOSS"], .7)
        self.assertEqual(row["five_grade_probabilities_unverified"]["FULL_WIN"], .3)

    def test_over_under_225_two_goals_half_loss_vs_half_win(self):
        over = assess({2: 1.0}, side="OVER", line=2.25, decimal_odds=2)
        under = assess({2: 1.0}, side="UNDER", line=2.25, decimal_odds=2)
        self.assertAlmostEqual(over["nominal_ev_per_unit_claimed_price"], -.5)
        self.assertAlmostEqual(under["nominal_ev_per_unit_claimed_price"], .5)
        self.assertEqual(over["five_grade_probabilities_unverified"]["HALF_LOSS"], 1)
        self.assertEqual(under["five_grade_probabilities_unverified"]["HALF_WIN"], 1)

    def test_integer_total_pushes(self):
        for side in ("UNDER", "OVER"):
            row = assess({3: 1}, side=side, line=3.0, decimal_odds=1.92)
            self.assertEqual(row["five_grade_probabilities_unverified"]["PUSH"], 1)
            self.assertEqual(row["nominal_ev_per_unit_claimed_price"], 0)

    def test_deep_total_675_needs_full_goal_distribution(self):
        over = assess({7: 1}, side="OVER", line=6.75, decimal_odds=2)
        under = assess({7: 1}, side="UNDER", line=6.75, decimal_odds=2)
        self.assertAlmostEqual(over["nominal_ev_per_unit_claimed_price"], .5)
        self.assertAlmostEqual(under["nominal_ev_per_unit_claimed_price"], -.5)

    def test_missing_total_distribution_never_uses_scalar_or_1x2(self):
        row = assess(None, side="OVER", line=2.75, decimal_odds=2)
        self.assertEqual(row["reason"], "NEEDS_FULL_TOTAL_GOAL_DISTRIBUTION")
        self.assertIsNone(row["nominal_ev_per_unit_claimed_price"])
        self.assertEqual(row["production_recommendations"], "DISABLED")

    def test_low_odds_closes_even_when_hypothetical_ev_positive(self):
        row = assess({4: 1}, side="OVER", line=2.25, decimal_odds=1.79,
                     conservative_goal_lower_bounds={4: .98}, quote_age_seconds=1)
        self.assertEqual(row["reason"], "ODDS_BELOW_MINIMUM")
        self.assertFalse(row["research_value_screen_pass"])

    def test_conservative_lower_mass_and_quote_are_necessary(self):
        base = {2: .2, 3: .8}
        lower = {2: .1, 3: .72}
        row = assess(base, side="OVER", line=2.75, decimal_odds=2,
                     conservative_goal_lower_bounds=lower, quote_age_seconds=20)
        self.assertAlmostEqual(row["nominal_ev_per_unit_claimed_price"], .2)
        self.assertAlmostEqual(row["conservative_ev_lower_bound_if_claims_valid"], .08)
        self.assertTrue(row["research_value_screen_pass"])
        self.assertEqual(row["status"], "RESEARCH_ONLY")
        self.assertFalse(row["quote_executable_authenticated"])
        self.assertFalse(row["positive_expected_value_verified"])
        self.assertFalse(row["can_enter_formal_settlement_ledger"])
        self.assertIsNone(row["recommended_stake"])
        self.assertEqual(row["formal_bet_count"], 0)
        self.assertEqual(row["production_recommendations"], "DISABLED")
        stale = assess(base, side="OVER", line=2.75, decimal_odds=2,
                       conservative_goal_lower_bounds=lower, quote_age_seconds=121)
        self.assertEqual(stale["status"], "HOLD")
        self.assertEqual(stale["reason"], "MISSING_OR_STALE_CLAIMED_QUOTE")

    def test_positive_nominal_but_negative_lower_bound_holds(self):
        row = assess({2: .2, 3: .8}, side="OVER", line=2.75, decimal_odds=2,
                     conservative_goal_lower_bounds={2: .1, 3: .3},
                     quote_age_seconds=20)
        self.assertGreater(row["nominal_ev_per_unit_claimed_price"], 0)
        self.assertLess(row["conservative_ev_lower_bound_if_claims_valid"], 0)
        self.assertEqual(row["reason"], "INSUFFICIENT_CONSERVATIVE_TOTAL_EV")

    def test_invalid_probability_distribution_and_aliases_refused(self):
        for dist in ({2: .7, 3: .7}, {2: True, 3: 0}, {"02": 1},
                     {0: .5, "0": .5}, {41: 1}, {-1: 1}, {"2.5": 1},
                     {2: float("nan")}, [], {}):
            with self.subTest(dist=dist):
                row = assess(dist, side="OVER", line=2.75, decimal_odds=2)
                self.assertEqual(row["status"], "HOLD")
                self.assertFalse(row["research_value_screen_pass"])

    def test_invalid_prices_lines_and_claims_fail_closed(self):
        for price in (True, -1, 1, float("inf"), float("nan"), 101):
            row = assess({3: 1}, side="OVER", line=2.75, decimal_odds=price)
            self.assertEqual(row["reason"], "INVALID_DECIMAL_PRICE")
        for line in (True, .1, 0, 15.25, float("nan"), "2.75"):
            row = assess({3: 1}, side="OVER", line=line, decimal_odds=2)
            self.assertEqual(row["status"], "HOLD")
            self.assertIsNone(row["nominal_ev_per_unit_claimed_price"])
        bad = assess({2: .2, 3: .8}, side="OVER", line=2.75,
                     decimal_odds=2,
                     conservative_goal_lower_bounds={3: .81})
        self.assertEqual(bad["reason"], "INVALID_CONSERVATIVE_TOTAL_LOWER_BOUNDS")
        self.assertEqual(assess({2: 1}, side="HOME", line=2.75)["reason"],
                         "INVALID_TOTAL_DIRECTION")


if __name__ == "__main__":
    unittest.main()
