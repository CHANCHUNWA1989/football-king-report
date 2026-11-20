"""Offline tests for exact full-time over/under 2.5 settlement."""
import unittest
from ops.historical_total_2_5_settlement import settle_total_2_5, flat_stake_profit


class HistoricalTotal25SettlementTests(unittest.TestCase):
    def test_over_wins_on_three_goals(self):
        self.assertEqual(settle_total_2_5(2, 1, "Over"), "WIN")

    def test_over_loses_on_two_goals(self):
        self.assertEqual(settle_total_2_5(1, 1, "Over"), "LOSS")

    def test_under_wins_on_two_goals(self):
        self.assertEqual(settle_total_2_5(1, 1, "Under"), "WIN")

    def test_under_loses_on_three_goals(self):
        self.assertEqual(settle_total_2_5(0, 3, "Under"), "LOSS")

    def test_profit(self):
        self.assertEqual(flat_stake_profit("WIN", 1.95), 0.95)
        self.assertEqual(flat_stake_profit("LOSS", 1.95), -1)

    def test_invalid_score(self):
        with self.assertRaises(ValueError):
            settle_total_2_5(-1, 2, "Over")

    def test_invalid_odds(self):
        with self.assertRaises(ValueError):
            flat_stake_profit("WIN", 1)


if __name__ == "__main__":
    unittest.main()
