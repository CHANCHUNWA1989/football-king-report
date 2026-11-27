import unittest
from ops.v5_integration_acceptance import grid,project,summary,settlement,cross_engine,readiness

class AcceptanceTest(unittest.TestCase):
    def test_mass_and_projection(self):
        g=grid(1,0,.7,.9);s=summary(g)
        for p in (s["1x2"],s["final_total_p"].values(),s["final_margin_p"].values()):
            self.assertAlmostEqual(sum(p),1)
        self.assertAlmostEqual(s["1x2"][1],s["final_margin_p"]["0"])
        for kind,side,line in (("handicap","away",.25),("totals","over",2.25)):
            self.assertAlmostEqual(sum(project(g,kind,side,line).values()),1)
    def test_exact_quarter_lines(self):
        self.assertEqual(settlement(1,0,"handicap","home",-1.25),"HALF_LOSS")
        self.assertEqual(settlement(1,1,"totals","under",2.25),"HALF_WIN")
        self.assertEqual(settlement(2,1,"totals","over",2.75),"HALF_WIN")
        self.assertEqual(settlement(0,0,"handicap","home",0),"PUSH")
    def test_zero_remaining(self):
        g=grid(2,1,0,0)
        self.assertEqual(summary(g)["1x2"],[1,0,0])
        self.assertEqual(project(g,"totals","over",2.75)["HALF_WIN"],1)
    def test_invalid(self):
        for rate in (True,float("nan"),-1,9):
            with self.assertRaises(ValueError):grid(0,0,rate,1)
        for line in (True,.3,float("inf")):
            with self.assertRaises(ValueError):settlement(0,0,"handicap","home",line)
    def test_engines(self):
        self.assertEqual(cross_engine(),8820)
    def test_release_cannot_enable(self):
        e={"production_recommendations":"DISABLED","samples":[{}],"n":1}
        q={"production_recommendations":"DISABLED","passed":7,"total":7}
        m={"production_recommendations":"DISABLED","collection_status":"PASS"}
        r=readiness(e,q,m)
        self.assertEqual(r["release_status"],"HOLD")
        self.assertEqual(r["independently_authenticated_forward_samples"],0)
        self.assertFalse(r["production_deployed"])
        with self.assertRaises(ValueError):readiness(e,q,{**m,"production_recommendations":"ENABLED"})
