import unittest
from ops.research_unified_snapshot_audit_v1 import audit

class SnapshotAuditTests(unittest.TestCase):
    def setUp(self):
        self.args=dict(fixture_id="synthetic",kickoff="2026-11-27T20:15:00+08:00",
                       as_of="2026-11-27T20:12:00+08:00",quote_at="2026-11-27T20:11:00+08:00",
                       rates_at="2026-11-27T20:00:00+08:00",
                       odds={"home":2.28,"draw":3.50,"away":2.45},rates=(1.56,1.77))
    def check_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for key in ("certified_ev","source_authenticity_verified","independent_oos_proven","model_promotion_allowed"):
            self.assertIs(r[key],False)
    def test_market_arithmetic(self):
        r=audit(**self.args)
        self.check_hold(r)
        self.assertTrue(r["structural_audit_passed"])
        self.assertEqual(r["scenario_count"],9)
        m=sum(1/v for v in self.args["odds"].values())
        self.assertAlmostEqual(r["overround"],m-1)
        self.assertAlmostEqual(sum(v["market_probability"] for v in r["one_x_two"].values()),1)
        self.assertAlmostEqual(sum(v["scenario_probability"] for v in r["one_x_two"].values()),1)
        for key,x in r["one_x_two"].items():
            self.assertAlmostEqual(x["market_probability"],1/self.args["odds"][key]/m)
            self.assertAlmostEqual(x["hypothetical_ev"],self.args["odds"][key]*x["scenario_probability"]-1)
            self.assertLessEqual(x["scenario_probability_range"][0],x["scenario_probability"])
            self.assertGreaterEqual(x["scenario_probability_range"][1],x["scenario_probability"])
    def test_invalid_snapshots(self):
        cases=[{"quote_at":"2026-11-27T20:06:59+08:00"},
               {"quote_at":"2026-11-27T20:13:00+08:00"},
               {"rates_at":"2026-11-27T20:13:00+08:00"},
               {"as_of":"2026-11-27T20:15:00+08:00"},
               {"quote_at":"2026-11-27T20:11:00"},
               {"odds":{"home":2.28,"away":2.45}},
               {"odds":{"home":True,"draw":3.50,"away":2.45}},
               {"rates":(float("nan"),1.77)},
               {"rates":(1.56,False)},
               {"fixture_id":""},
               {"asian":[{"market":"totals","selection":"over","line":2.3,"decimal_odds":1.9}]}]
        for change in cases:
            with self.subTest(change=change):
                r=audit(**{**self.args,**change})
                self.check_hold(r)
                self.assertFalse(r["structural_audit_passed"])
                self.assertNotIn("one_x_two",r)
    def test_age_boundary(self):
        r=audit(**{**self.args,"quote_at":"2026-11-27T20:07:00+08:00"})
        self.assertTrue(r["structural_audit_passed"])
        self.assertEqual(r["quote_age_seconds"],300)
    def test_equivalent_utc(self):
        r=audit(**self.args)
        x=audit(**{**self.args,"quote_at":"2026-11-27T12:11:00Z"})
        self.assertEqual(r,x)
    def test_totals_and_asian_same_matrix(self):
        r=audit(**self.args,asian=[{"market":"totals","selection":"over","line":2.5,"decimal_odds":1.9},
                                {"market":"handicap","selection":"home","line":-0.25,"decimal_odds":1.9}])
        self.check_hold(r)
        self.assertTrue(r["structural_audit_passed"])
        p=r["goal_scenarios"]["over_2_5"]["base"]
        self.assertAlmostEqual(r["asian"][0]["base"]["expected_net_return"],1.9*p-1)
        for row in r["asian"]:
            self.assertAlmostEqual(sum(row["base"]["outcome_probabilities"].values()),1)
            self.assertLessEqual(row["hypothetical_ev_range"][0],row["base"]["expected_net_return"])
            self.assertGreaterEqual(row["hypothetical_ev_range"][1],row["base"]["expected_net_return"])
    def test_large_gap_never_promotes(self):
        r=audit(**{**self.args,"odds":{"home":1.08,"draw":7.5,"away":13},"rates":(2.17,1.17)})
        self.check_hold(r)
        self.assertTrue(r["structural_audit_passed"])
        self.assertTrue(r["one_x_two"]["home"]["large_market_gap"])
        self.assertGreater(r["one_x_two"]["away"]["hypothetical_ev"],0)
    def test_goal_range_includes_base(self):
        r=audit(**self.args)
        for x in r["goal_scenarios"].values():
            self.assertLess(x["range"][0],x["base"])
            self.assertGreater(x["range"][1],x["base"])
if __name__=="__main__":
    unittest.main()
