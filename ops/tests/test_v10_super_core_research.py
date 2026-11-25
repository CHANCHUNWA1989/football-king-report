"""Offline V10 core regression checks."""
import unittest
from datetime import date,timedelta
from ops import v10_super_core_research as v
from ops.v9_fixed_history_benchmark import predict,probs

class V10Tests(unittest.TestCase):
    def test_internal_checks(self):
        self.assertEqual(v.selftest(),8)
    def test_dc_correction(self):
        for h,a in ((.05,.05),(1.5,1.1),(8,8),(8,.05)):
            p=probs(h,a);q=v.dc(p,(h,a))
            self.assertAlmostEqual(sum(q),1.)
            self.assertGreater(q[1],p[1])
            self.assertTrue(all(x>0 for x in q))
    def test_elo_symmetry_without_home_advantage(self):
        p=v.elo_prob(1500,1560,.25)
        for x,y in zip(p,(.375,.25,.375)):self.assertAlmostEqual(x,y)
    def test_earlier_only_fitting(self):
        p={m:(.7,.2,.1) for m in v.RAW}
        a=[{"y":0,"p":p} for _ in range(500)]
        b=[{"y":2,"p":p} for _ in range(20)]
        c=[{"y":0,"p":p} for _ in range(20)]
        ra=v.evaluate({2024:{"L":a},2025:{"L":b}})
        rb=v.evaluate({2024:{"L":a},2025:{"L":c}})
        for key in ("weights","dynamic_calibration","adaptive_calibration","development_n"):
            self.assertEqual(ra["folds"][1][key],rb["folds"][1][key])
        self.assertEqual(ra["causal_confidence_selection"]["rules"],rb["causal_confidence_selection"]["rules"])
        self.assertEqual(ra["causal_confidence_selection"]["rules"][0]["threshold"],None)
        self.assertIsNotNone(ra["causal_confidence_selection"]["rules"][1]["threshold"])
        self.assertEqual(ra["rolling"]["adaptive_calibrated"]["n"],520)
    def test_weights_and_no_promotion(self):
        p=dict(zip(v.RAW,((.8,.1,.1),(.1,.1,.8),(.5,.3,.2),(.6,.2,.2))))
        rows=[{"p":p,"y":0} for _ in range(500)]
        w=v.weights(rows)
        self.assertAlmostEqual(sum(w),1.)
        self.assertGreater(w[0],w[1])
        self.assertGreaterEqual(min(w),.125)
        result=v.evaluate({2025:{"L":rows}})
        self.assertEqual(result["verified_forward_sample_credit"],0)
        self.assertFalse(result["automatic_promotion"])
    def test_cluster_ci_deterministic(self):
        p={m:(.6,.2,.2) for m in v.MODELS};p["adaptive_calibrated"]=(.8,.1,.1)
        rows=[{"year":y,"league":"L","p":p,"y":0} for y in range(2011,2017)]
        a=v.paired_blocks(rows,"adaptive_calibrated")
        self.assertEqual(a,v.paired_blocks(rows,"adaptive_calibrated"))
        self.assertGreater(a["log_loss_reduction_ci"][0],0)
        self.assertEqual(a["accuracy_delta_ci"],[0,0])
    def test_optional_rates_compatibility(self):
        train=[(date(2018,8,1)+timedelta(days=i),"A","B",2,1) for i in range(100)]
        test=[(date(2019,8,1),"A","B",1,0)]
        self.assertEqual(predict(train,test),[r[:6] for r in predict(train,test,include_rates=True)])
if __name__=="__main__":
    unittest.main()
