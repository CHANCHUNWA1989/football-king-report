"""Synthetic-only parlay regression tests; no external fixtures or quotes."""
import unittest
from decimal import Decimal
from ops.parlay_settlement import parlay_return, PRODUCTION_RECOMMENDATIONS, POSITIVE_EV_VERIFIED

def leg(market, side, line, h, a, odds):
    return dict(market=market, side=side, line=line, home_goals=h, away_goals=a, odds=odds)

class ParlaySettlementTests(unittest.TestCase):
    def test_two_full_wins(self):
        self.assertEqual(parlay_return(10, [leg("total","under",2.5,0,0,1.87),leg("total","under",3.25,1,1,1.84)]), (Decimal("34.4080"),Decimal("24.4080")))
    def test_any_full_loss_zero_payout(self):
        self.assertEqual(parlay_return(10,[leg("total","under",2.5,0,0,1.87),leg("handicap","home",-1,0,1,4.2)]),(Decimal(0),Decimal(-10)))
    def test_half_win_factor(self):
        self.assertEqual(parlay_return(10,[leg("total","under",3.25,2,1,1.84)]),(Decimal("14.20"),Decimal("4.20")))
    def test_half_loss_factor(self):
        self.assertEqual(parlay_return(10,[leg("total","over",3.25,2,1,1.89)]),(Decimal("5.0"),Decimal("-5.0")))
    def test_push_factor(self):
        self.assertEqual(parlay_return(10,[leg("handicap","home",-1,2,1,4.2),leg("total","under",2.5,0,0,1.87)]),(Decimal("18.70"),Decimal("8.70")))
    def test_empty_rejected(self):
        with self.assertRaises(ValueError): parlay_return(10,[])
    def test_negative_stake_rejected(self):
        with self.assertRaises(ValueError): parlay_return(-1,[leg("total","under",2.5,0,0,1.87)])
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError): parlay_return("NaN",[leg("total","under",2.5,0,0,1.87)])
    def test_invalid_leg_rejected(self):
        with self.assertRaises(ValueError): parlay_return(10,[{}])
    def test_hold(self):
        self.assertEqual(PRODUCTION_RECOMMENDATIONS,"DISABLED")
        self.assertFalse(POSITIVE_EV_VERIFIED)

if __name__ == "__main__":
    unittest.main()
