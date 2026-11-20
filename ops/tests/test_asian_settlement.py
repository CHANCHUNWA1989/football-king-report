"""Synthetic regression cases for issue #450. No external providers."""
import unittest
from decimal import Decimal
from ops.asian_settlement import settle, expected_profit, PRODUCTION_RECOMMENDATIONS, POSITIVE_EV_VERIFIED

class AsianSettlementTests(unittest.TestCase):
    def test_handicap_full_loss(self):
        self.assertEqual(settle("handicap", "home", -1, 0, 1, 4.2), Decimal("-1"))
    def test_handicap_push(self):
        self.assertEqual(settle("handicap", "home", -1, 2, 1, 4.2), Decimal("0"))
    def test_handicap_win(self):
        self.assertEqual(settle("handicap", "home", -1, 3, 1, 4.2), Decimal("3.2"))
    def test_total_over_325_three_goals_half_loss(self):
        self.assertEqual(settle("total", "over", 3.25, 2, 1, 1.89), Decimal("-0.5"))
    def test_total_under_325_three_goals_half_win(self):
        self.assertEqual(settle("total", "under", 3.25, 2, 1, 1.84), Decimal("0.42"))
    def test_under_25_zero(self):
        self.assertEqual(settle("total", "under", 2.5, 0, 0, 1.87), Decimal("0.87"))
    def test_over_325_four(self):
        self.assertEqual(settle("total", "over", 3.25, 2, 2, 1.89), Decimal("0.89"))
    def test_negative_quarter_handicap(self):
        self.assertEqual(settle("handicap", "home", -0.25, 0, 0, 2), Decimal("-0.5"))
    def test_ev_exact(self):
        self.assertEqual(expected_profit("total", "under", 2.5, 2, {(0,0):"0.6",(2,2):"0.4"}), Decimal("0.2"))
    def test_bad_line(self):
        with self.assertRaises(ValueError):
            settle("total", "over", 2.3, 1, 1, 2)
    def test_negative_total_lines_rejected(self):
        for side in ("over", "under"):
            for line in ("-0.25", "-0.5", "-0.75", "-1.0"):
                with self.subTest(side=side, line=line), self.assertRaises(ValueError):
                    settle("total", side, line, 0, 0, "1.80")
    def test_nonnegative_total_boundary_returns(self):
        # Hand-calculated net returns at odds 1.80, not real betting evidence.
        cases = (("over", "0", 0, "0"), ("under", "0", 0, "0"),
                 ("over", "0.25", 0, "-0.5"), ("under", "0.25", 0, "0.4"),
                 ("over", "0.5", 0, "-1"), ("under", "0.5", 0, "0.8"),
                 ("over", "0.75", 1, "0.4"), ("under", "0.75", 1, "-0.5"),
                 ("over", "0.5", 1, "0.8"), ("under", "0.5", 1, "-1"),
                 ("over", "1", 1, "0"), ("under", "1", 1, "0"))
        for side, line, goals, net in cases:
            with self.subTest(side=side, line=line, goals=goals):
                self.assertEqual(settle("total", side, line, goals, 0, "1.80"),
                                 Decimal(net))
    def test_negative_handicap_lines_remain_valid(self):
        cases = (("home", "-0.25", 0, 0, "-0.5"),
                 ("home", "-1.0", 2, 1, "0"),
                 ("away", "-0.25", 1, 1, "-0.5"),
                 ("away", "-1.0", 1, 2, "0"))
        for side, line, home, away, net in cases:
            with self.subTest(side=side, line=line):
                self.assertEqual(settle("handicap", side, line, home, away, "1.80"),
                                 Decimal(net))
    def test_bad_probabilities(self):
        with self.assertRaises(ValueError):
            expected_profit("total", "over", 2.5, 2, {(1,1):"0.7"})
    def test_hold(self):
        self.assertEqual(PRODUCTION_RECOMMENDATIONS, "DISABLED")
        self.assertFalse(POSITIVE_EV_VERIFIED)

if __name__ == "__main__":
    unittest.main()
