import unittest
from ops.research_asian_settlement_v1 import asian_ev

class AsianSettlementTests(unittest.TestCase):
    def one(self,h,a,size=5):
        m=[[0.]*size for _ in range(size)]
        m[h][a]=1.
        return m
    def ev(self,m,market,selection,line,odds=2.):
        return asian_ev(m,market=market,selection=selection,line=line,decimal_odds=odds)
    def test_full_and_push(self):
        self.assertAlmostEqual(self.ev(self.one(2,1),"handicap","home",-0.5)["expected_net_return"],1)
        self.assertAlmostEqual(self.ev(self.one(2,1),"handicap","home",-1)["expected_net_return"],0)
    def test_half_win(self):
        r=self.ev(self.one(2,1),"handicap","home",-0.75)
        self.assertAlmostEqual(r["expected_net_return"],0.5)
        self.assertAlmostEqual(r["outcome_probabilities"]["half_win"],1)
    def test_half_loss(self):
        r=self.ev(self.one(2,1),"handicap","away",-0.75)
        self.assertAlmostEqual(r["expected_net_return"],-0.5)
    def test_total_quarter(self):
        self.assertAlmostEqual(self.ev(self.one(2,1),"totals","over",2.75)["expected_net_return"],0.5)
        self.assertAlmostEqual(self.ev(self.one(2,1),"totals","under",2.75)["expected_net_return"],-0.5)
    def test_opposite_sides(self):
        m=self.one(0,2)
        self.assertAlmostEqual(self.ev(m,"handicap","away",0.5)["expected_net_return"],1)
    def test_invalid_inputs(self):
        for line in (0.3,float("nan"),21):
            with self.assertRaises(ValueError):self.ev(self.one(1,1),"totals","over",line)
        with self.assertRaises(ValueError):self.ev(self.one(1,1),"totals","over",2.5,1)
    def test_fail_closed(self):
        r=self.ev(self.one(1,1),"totals","under",2.5)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["executable_quote_verified"])

if __name__=="__main__":unittest.main()
