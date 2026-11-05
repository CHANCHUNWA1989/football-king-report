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
    def test_bad_probabilities(self):
        with self.assertRaises(ValueError):
            expected_profit("total", "over", 2.5, 2, {(1,1):"0.7"})
    def test_hold(self):
        self.assertEqual(PRODUCTION_RECOMMENDATIONS, "DISABLED")
        self.assertFalse(POSITIVE_EV_VERIFIED)

if __name__ == "__main__":
    unittest.main()
