"""Fail-closed paper-only Kelly research, including exact Asian settlements."""
import math
import unittest

from ops.asian_ev_research import asian_net
from ops.kelly_research import (
    PRODUCTION_RECOMMENDATIONS, assess, theoretical_kelly,
)


class KellyResearchTests(unittest.TestCase):
    def test_binary_full_kelly_closed_form(self):
        case = theoretical_kelly({1: .55, -1: .45}, 0, 1.90)
        self.assertAlmostEqual(case["research_ev_per_unit"], .045)
        self.assertAlmostEqual(case["full_kelly_fraction"], .05, places=10)
        self.assertAlmostEqual(case["half_kelly_fraction"], .025, places=10)
        self.assertAlmostEqual(case["quarter_kelly_fraction"], .0125, places=10)
        self.assertGreater(case["hypothetical_log_growth"], 0)

    def test_deep_quarter_handicap_uses_half_win_not_full_win(self):
        # Selected team -0.75, margin 1 = half-win, margin 0 = full loss.
        self.assertAlmostEqual(asian_net(1, -.75, 2.0), .5)
        case = theoretical_kelly({1: .8, 0: .2}, -.75, 2.0)
        self.assertAlmostEqual(case["research_ev_per_unit"], .2)
        self.assertAlmostEqual(case["full_kelly_fraction"], .4, places=10)

    def test_positive_quarter_handicap_draw_is_half_win(self):
        self.assertAlmostEqual(asian_net(0, .25, 2.0), .5)
        case = theoretical_kelly({1: .4, 0: .3, -1: .3}, .25, 2.0)
        self.assertAlmostEqual(case["research_ev_per_unit"], .25)
        self.assertTrue(0 < case["full_kelly_fraction"] < 1)

    def test_under_total_integer_push_and_correct_sign(self):
        # For UNDER 3, use negative total goals + a POSITIVE line.
        self.assertEqual(asian_net(-3, 3.0, 2.0), 0)
        self.assertEqual(asian_net(-2, 3.0, 2.0), 1)
        self.assertEqual(asian_net(-4, 3.0, 2.0), -1)
        case = theoretical_kelly({-2: .4, -3: .3, -4: .3}, 3.0, 2.0)
        self.assertAlmostEqual(case["research_ev_per_unit"], .1)
        self.assertAlmostEqual(case["full_kelly_fraction"], 1 / 7, places=10)

    def test_negative_and_zero_ev_never_size(self):
        for distribution in ({1: .4, -1: .6}, {1: .5, -1: .5}):
            case = theoretical_kelly(distribution, 0, 2.0)
            self.assertEqual(case["full_kelly_fraction"], 0.0)
            self.assertEqual(case["quarter_kelly_fraction"], 0.0)

    def test_reject_impossible_no_downside_distribution(self):
        with self.assertRaisesRegex(ValueError, "NO_DOWNSIDE"):
            theoretical_kelly({1: .8, 0: .2}, 0, 2.0)

    def test_reject_invalid_inputs(self):
        samples = [
            ({1: .6, -1: .3}, 0, 2.0),
            ({1: True}, 0, 2.0),
            ({1: float("nan")}, 0, 2.0),
            ({True: 1.0}, 0, 2.0),
            ({1: 1.0}, .3, 2.0),
            ({1: .6, -1: .4}, True, 2.0),
            ({1: .6, -1: .4}, 0, True),
            ({1: .6, -1: .4}, 0, 1.0),
            ({1: .6, -1: .4}, 0, 999),
            ({1: .6, -1: .4}, 0, float("inf")),
        ]
        for distribution, line, odds in samples:
            with self.subTest(case=(distribution, line, odds)):
                with self.assertRaises(ValueError):
                    theoretical_kelly(distribution, line, odds)

    def test_unverified_real_case_always_hold_without_math_output(self):
        case = assess({1: .99, -1: .01}, 0, 99.0)
        self.assertEqual(case["status"], "HOLD")
        self.assertIsNone(case["research_ev_per_unit"])
        self.assertIsNone(case["full_kelly_fraction"])
        self.assertIsNone(case["suggested_stake"])
        self.assertFalse(case["bet_eligible"])
        self.assertEqual(case["production_recommendations"], "DISABLED")

    def test_hypothetical_opt_in_is_never_approved_or_a_stake(self):
        case = assess({1: .55, -1: .45}, 0, 1.90, hypothetical=True)
        self.assertEqual(case["status"], "HYPOTHETICAL_ONLY")
        self.assertAlmostEqual(case["full_kelly_fraction"], .05)
        self.assertFalse(case["independent_probability_calibration_verified"])
        self.assertFalse(case["executable_quote_verified"])
        self.assertFalse(case["bet_eligible"])
        self.assertIsNone(case["suggested_stake"])
        self.assertEqual(PRODUCTION_RECOMMENDATIONS, "DISABLED")

    def test_no_real_fraction_with_unverified_or_invalid_data(self):
        self.assertEqual(assess(hypothetical=False)["status"], "HOLD")
        self.assertIsNone(assess({1: "fake"}, 0, 2.0)["full_kelly_fraction"])


    def test_quarter_half_loss_and_under_quarter_half_win(self):
        # A +0.75 team selection losing by one goal loses only half.
        self.assertAlmostEqual(asian_net(-1, .75, 1.90), -.5)
        # UNDER 3.25 at exactly three goals wins half (UNDER 3 push,
        # UNDER 3.5 win). UNDER 2.75 at three goals loses half.
        self.assertAlmostEqual(asian_net(-3, 3.25, 1.90), .45)
        self.assertAlmostEqual(asian_net(-3, 2.75, 1.90), -.5)
        self.assertEqual(asian_net(-4, 3.25, 1.90), -1)
        case = theoretical_kelly({0: .55, -1: .45}, .75, 1.90)
        self.assertGreater(case["research_ev_per_unit"], 0)
        self.assertTrue(0 < case["full_kelly_fraction"] < 1)
        self.assertFalse(case["bet_eligible"])

    def test_numerical_solution_beats_fixed_grid_across_quarter_lines(self):
        # Independent arithmetic sanity check: objective at computed fraction
        # should dominate any of 100 equally spaced hypothetical fractions.
        # Only synthetic distributions; no real model probability claims.
        cases = (
            ({1: .55, -1: .45}, 0, 1.9),
            ({1: .8, 0: .2}, -.75, 2.0),
            ({1: .4, 0: .3, -1: .3}, .25, 2.0),
            ({-2: .4, -3: .3, -4: .3}, 3.0, 2.0),
            ({-1: .45, 0: .35, 1: .20}, .75, 1.92),
        )
        for distribution, line, odds in cases:
            with self.subTest(line=line, odds=odds):
                got = theoretical_kelly(distribution, line, odds)
                f = got["full_kelly_fraction"]
                growth = lambda fraction: sum(
                    p * math.log1p(fraction * asian_net(margin, line, odds))
                    for margin, p in distribution.items()
                )
                self.assertGreaterEqual(growth(f) + 1e-12,
                                        max(growth(i / 100) for i in range(100)))
                self.assertAlmostEqual(got["hypothetical_log_growth"],
                                       growth(f), places=11)

    def test_nominal_edge_disappears_under_probability_stress(self):
        # Demonstrates *why* a research estimate is NOT a Kelly stake:
        # plausible calibration error can reverse the sign of EV.
        nominal = theoretical_kelly({1: .55, -1: .45}, 0, 1.9)
        stressed = theoretical_kelly({1: .48, -1: .52}, 0, 1.9)
        self.assertGreater(nominal["research_ev_per_unit"], 0)
        self.assertLess(stressed["research_ev_per_unit"], 0)
        self.assertEqual(stressed["full_kelly_fraction"], 0)
        self.assertIsNone(nominal["suggested_stake"])
        self.assertIsNone(stressed["suggested_stake"])


    def test_unbounded_probability_buckets_rejected(self):
        # Safety: 96 optimization steps must not scale with arbitrary input.
        cases = {-128 + i: 1.0 / 257 for i in range(257)}
        with self.assertRaisesRegex(ValueError, "TOO_MANY_OUTCOMES"):
            theoretical_kelly(cases, 0, 2.0)

    def test_boundary_solution_is_labeled_as_capped(self):
        # Nearly all outcomes win; the true unconstrained optimum
        # exceeds 100% exposure when downside is only a half-loss.
        case = theoretical_kelly({1: .95, -1: .05}, .75, 2.0)
        self.assertTrue(case["optimization_at_fraction_cap"])
        self.assertGreater(case["full_kelly_fraction"], .99)
        self.assertIsNone(case["suggested_stake"])
        self.assertFalse(case["bet_eligible"])

if __name__ == "__main__":
    unittest.main()
