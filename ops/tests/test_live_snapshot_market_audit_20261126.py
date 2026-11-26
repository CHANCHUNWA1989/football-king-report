import unittest
from ops.live_snapshot_market_audit_20261126 import audit, freshness, implied, legs, profit

class SnapshotTests(unittest.TestCase):
    def test_screenshot(self):
        s={"captured_at":"2026-11-26T22:47:00+08:00","period":"FIRST_HALF",
           "minute":None,"independent_score_sources":[],"market_suspended":None,
           "one_x_two":[5.4,2.8,1.69],"three_way_home_plus_one":[1.93,3,3.45],
           "over_under_15":[1.84,1.86],"over_under_25":[3.65,1.23]}
        r=audit(s,s["captured_at"])
        self.assertAlmostEqual(sum(r["one_x_two"]),1)
        self.assertAlmostEqual(sum(r["totals_bins"]),1)
        self.assertAlmostEqual(r["one_x_two"][2],0.5218,places=3)
        self.assertIn("MINUTE_UNVERIFIED",r["reasons"])
        self.assertIn("SCORE_CORROBORATION_MISSING",r["reasons"])
        self.assertFalse(r["qualified"])
        self.assertFalse(r["positive_ev_verified"])
        s["over_under_15"]=[9,1.1]
        s["over_under_25"]=[1.1,9]
        self.assertIn("TOTALS_NOT_MONOTONE",audit(s,s["captured_at"])["reasons"])
    def test_clock(self):
        t="2026-11-26T22:47:00+08:00"
        self.assertTrue(freshness(t,"2026-11-26T14:48:00Z"))
        self.assertFalse(freshness(t,"2026-11-26T14:48:01Z"))
        self.assertFalse(freshness(t,"2026-11-26T14:46:59Z"))
        with self.assertRaises(ValueError): freshness("2026-11-26T22:47:00",t)
    def test_odds(self):
        for x in (1,0,-2,float("nan"),float("inf"),True):
            with self.subTest(x=x), self.assertRaises(ValueError): implied([x,2])
    def test_settlement_examples(self):
        self.assertAlmostEqual(profit(1,-0.75,2.12),0.56)
        self.assertAlmostEqual(profit(-1,0.75,1.66),-0.5)
        self.assertAlmostEqual(profit(-2,1.75,1.62),-0.5)
        self.assertAlmostEqual(profit(0,0,2),0)
        self.assertAlmostEqual(profit(1,-0.5,2),1)
    def test_settlement_stress(self):
        for m in range(-10,11):
            for q in range(-24,25):
                line=q/4
                for odds in (1.23,1.66,2.12,3.65):
                    with self.subTest(m=m,q=q,odds=odds):
                        p=profit(m,line,odds)
                        self.assertTrue(-1-1e-9<=p<=odds-1+1e-9)
                        self.assertAlmostEqual(profit(m,line,2)+profit(-m,-line,2),0)
                        if q%2:
                            self.assertAlmostEqual(p,(profit(m,(q-1)/4,odds)+profit(m,(q+1)/4,odds))/2)
    def test_invalid_line(self):
        for x in (0.1,float("nan"),True,31):
            with self.assertRaises(ValueError): legs(x)

if __name__=="__main__": unittest.main()
