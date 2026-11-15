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


if __name__ == "__main__":
    unittest.main()
