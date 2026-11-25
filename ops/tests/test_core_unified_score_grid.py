"""All inputs synthetic: no match result, quote, prediction seal or xG."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ops.core_unified_score_grid import (
    analyze, score_grid, one_x_two, three_way_handicap,
    asian_handicap, totals, RHO, MAX_GOALS,
)
from ops.shadow_forecast import poisson_1x2


class ScoreGridResearchTests(unittest.TestCase):
    def check_sum(self, d):
        self.assertAlmostEqual(sum(d.values()), 1, places=6)
        self.assertTrue(all(0 <= p <= 1 for p in d.values()))

    def test_genuine_matrix_is_normalized_at_typical_rates(self):
        grid, tail = score_grid(1.4, 1.1)
        self.assertEqual(len(grid), MAX_GOALS + 1)
        self.assertTrue(all(len(row) == MAX_GOALS + 1 for row in grid))
        self.assertAlmostEqual(math.fsum(map(math.fsum, grid)), 1, places=12)
        self.assertLess(tail["combined_tail_upper_bound"], 1e-7)

    def test_extreme_rates_do_not_lose_goal_mass(self):
        grid, tail = score_grid(5.5, 5.5)
        self.assertAlmostEqual(math.fsum(map(math.fsum, grid)), 1, places=12)
        self.assertLess(tail["combined_tail_upper_bound"], 1e-7)

    def test_rho_zero_matches_original_shadow_poisson_at_normal_rates(self):
        for home, away in ((1.2, 0.9), (1.7, 1.3), (.4, .6)):
            got = one_x_two(score_grid(home, away, rho=0)[0])
            expected = poisson_1x2(home, away)
            for idx, key in enumerate(("HOME", "DRAW", "AWAY")):
                self.assertAlmostEqual(got[key], expected[idx], places=6)

    def test_fixed_negative_rho_adds_low_score_draw_mass(self):
        old = one_x_two(score_grid(1.2, .9, rho=0)[0])
        new = one_x_two(score_grid(1.2, .9, rho=RHO)[0])
        self.assertGreater(new["DRAW"], old["DRAW"])
        self.assertLess(new["HOME"], old["HOME"])
        self.assertLess(new["AWAY"], old["AWAY"])

    def test_equal_rates_preserve_home_away_symmetry(self):
        p = one_x_two(score_grid(1.2, 1.2)[0])
        self.assertAlmostEqual(p["HOME"], p["AWAY"], places=12)

    def test_hkjc_threeway_minus1_is_exact_win_margin_partition(self):
        grid, _ = score_grid(1.5, .9)
        market = three_way_handicap(grid, home_handicap=-1)
        one_x = one_x_two(grid)
        self.check_sum(market)
        self.assertAlmostEqual(market["HOME"] + market["DRAW"],
                               one_x["HOME"], places=12)
        manual = math.fsum(grid[h][a] for h in range(25)
                           for a in range(25) if h - a == 1)
        self.assertAlmostEqual(market["DRAW"], manual, places=12)

    def test_hkjc_threeway_plus1_exact_away_win_partition(self):
        grid, _ = score_grid(1.2, 1.6)
        p = three_way_handicap(grid, home_handicap=1)
        one_x = one_x_two(grid)
        self.check_sum(p)
        self.assertAlmostEqual(p["DRAW"] + p["AWAY"],
                               one_x["AWAY"], places=12)

    def test_hkjc_handicap_draw_is_not_push(self):
        grid, _ = score_grid(1.4, 1.1)
        threeway = three_way_handicap(grid, home_handicap=-1)
        asian = asian_handicap(grid, side="HOME", line=-1)
        self.assertGreater(threeway["DRAW"], 0)
        self.assertAlmostEqual(threeway["DRAW"], asian["PUSH"], places=12)
        # They have equal event probability, but opposite financial settlement.
        self.assertIn("DRAW", threeway)
        self.assertNotIn("PUSH", threeway)

    def test_asian_minus_three_quarters_has_half_win(self):
        p = asian_handicap(score_grid(1.5, 1.0)[0], side="HOME", line=-.75)
        self.check_sum(p)
        self.assertGreater(p["HALF_WIN"], 0)
        self.assertAlmostEqual(p["PUSH"], 0, places=12)

    def test_opposite_asian_sides_have_reversed_grade_probabilities(self):
        result = analyze(1.4, 1.3)
        home, away = result["asian_home_minus_0_75"], result["asian_away_plus_0_75"]
        pairs = (("FULL_WIN", "FULL_LOSS"), ("HALF_WIN", "HALF_LOSS"),
                 ("PUSH", "PUSH"), ("HALF_LOSS", "HALF_WIN"),
                 ("FULL_LOSS", "FULL_WIN"))
        for left, right in pairs:
            self.assertAlmostEqual(home[left], away[right], places=6)

    def test_total_over_and_under_two_point_five_complement(self):
        grid, _ = score_grid(1.6, .9)
        over = totals(grid, side="OVER", line=2.5)
        under = totals(grid, side="UNDER", line=2.5)
        self.check_sum(over); self.check_sum(under)
        self.assertAlmostEqual(over["FULL_WIN"] + under["FULL_WIN"], 1, places=12)
        self.assertAlmostEqual(over["PUSH"], 0, places=12)
        self.assertAlmostEqual(under["PUSH"], 0, places=12)

    def test_integer_total_has_real_push_outcome(self):
        p = totals(score_grid(1.4, 1.1)[0], side="OVER", line=3.0)
        self.check_sum(p)
        self.assertGreater(p["PUSH"], 0)

    def test_quarter_total_has_half_win_and_half_loss(self):
        g = score_grid(1.4, 1.1)[0]
        over = totals(g, side="OVER", line=2.75)
        under = totals(g, side="UNDER", line=2.75)
        self.check_sum(over); self.check_sum(under)
        self.assertGreater(over["HALF_WIN"], 0)
        self.assertGreater(under["HALF_LOSS"], 0)

    def test_all_reported_market_marginals_are_normalized(self):
        r = analyze(1.57, 1.27)
        for name in ("full_time_1x2", "hkjc_three_way_home_minus_1",
                     "hkjc_three_way_home_plus_1", "asian_home_minus_0_75",
                     "asian_away_plus_0_75", "total_over_2_5",
                     "total_under_2_5"):
            self.check_sum(r[name])

    def test_research_output_never_claims_betting_or_model_calibration(self):
        r = analyze(1.57, 1.27)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        for key in ("model_probabilities_calibrated", "verified_positive_ev",
                    "prospective_forecast_seal_verified",
                    "quoted_bookmaker_market_available", "automated_bets",
                    "eligible_for_formal_oos_scoring",
                    "half_time_and_next_goal_model_available"):
            self.assertFalse(r[key])
        self.assertNotIn("bookmaker_odds", r)
        self.assertNotIn("recommended_stake", r)

    def test_bad_goal_rates_are_rejected(self):
        for bad in (True, False, None, "1.4", 0, -1, 5.501,
                    float("nan"), float("inf"), 10**1000):
            with self.subTest(rate=repr(bad)[:30]):
                with self.assertRaises((ValueError, OverflowError)):
                    score_grid(bad, 1.2)

    def test_rho_fitting_after_the_match_is_not_an_option(self):
        for bad in (True, None, -0.15, 0.025, .5, float("nan"), "0"):
            with self.subTest(rho=repr(bad)):
                with self.assertRaises(ValueError):
                    score_grid(1.2, 1.1, rho=bad)

    def test_bad_threeway_asian_and_total_market_lines_rejected(self):
        g = score_grid(1.3, 1.2)[0]
        for bad in (0.75, True, "1", 0, 3):
            with self.assertRaises(ValueError):
                three_way_handicap(g, home_handicap=bad)
        with self.assertRaises(ValueError):
            asian_handicap(g, side="HOME", line=.33)
        with self.assertRaises(ValueError):
            asian_handicap(g, side="BOTH", line=.25)
        with self.assertRaises(ValueError):
            totals(g, side="BOTH", line=2.5)
        with self.assertRaises(ValueError):
            totals(g, side="UNDER", line=0.0)

    def test_unsupported_asian_time_markets_not_falsely_claimed(self):
        r = analyze(1.2, 1.4)
        self.assertFalse(r["live_event_or_xg_authenticated"])
        self.assertFalse(r["half_time_and_next_goal_model_available"])
        self.assertTrue(r["probabilities_from_exactly_one_score_grid"])
        self.assertTrue(r["all_market_internal_consistency_passed"])
        self.assertEqual(r["model"], "unified-score-grid-fixed-dc-minus005-research-v1")


if __name__ == "__main__":
    unittest.main()
