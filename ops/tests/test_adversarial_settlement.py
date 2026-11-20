"""Adversarial research-only regression checks for settlement safety."""
import unittest
from decimal import Decimal
from ops.asian_settlement import settle, expected_profit
from ops.parlay_settlement import parlay_return

def leg(side, line, h, a, odds="2"):
    return dict(market="handicap",side=side,line=line,home_goals=h,away_goals=a,odds=odds)

class AdversarialSettlementTests(unittest.TestCase):
    def test_away_negative_quarter_draw_half_loss(self):
        self.assertEqual(settle("handicap","away","-0.25",0,0,2),Decimal("-0.5"))
    def test_home_positive_quarter_draw_half_win(self):
        self.assertEqual(settle("handicap","home","0.25",0,0,2),Decimal("0.5"))
    def test_under_275_three_half_loss(self):
        self.assertEqual(settle("total","under","2.75",2,1,2),Decimal("-0.5"))
    def test_over_275_three_half_win(self):
        self.assertEqual(settle("total","over","2.75",2,1,2),Decimal("0.5"))
    def test_exact_total_push(self):
        self.assertEqual(settle("total","over",3,2,1,2),Decimal(0))
    def test_negative_score_rejected(self):
        with self.assertRaises(ValueError): settle("total","under",2.5,-1,1,2)
    def test_fractional_score_rejected(self):
        with self.assertRaises(ValueError): settle("total","under",2.5,1.5,1,2)
    def test_nonfinite_odds_rejected(self):
        with self.assertRaises(ValueError): settle("total","under",2.5,0,0,"Infinity")
    def test_invalid_market_rejected(self):
        with self.assertRaises(ValueError): settle("moneyline","home",0,1,0,2)
    def test_missing_leg_field_rejected(self):
        with self.assertRaises(ValueError): parlay_return(10,[{"market":"total"}])
    def test_push_and_half_loss_accumulator(self):
        gross,net=parlay_return(10,[leg("home",-1,2,1),dict(market="total",side="over",line=3.25,home_goals=2,away_goals=1,odds=2)])
        self.assertEqual((gross,net),(Decimal("5.0"),Decimal("-5.0")))
    def test_zero_prob_mass_rejected(self):
        with self.assertRaises(ValueError): expected_profit("total","over",2.5,2,{})
    def test_no_unverified_positive_ev_certification(self):
        from ops.asian_settlement import POSITIVE_EV_VERIFIED
        self.assertFalse(POSITIVE_EV_VERIFIED)

if __name__=="__main__":
    unittest.main()
