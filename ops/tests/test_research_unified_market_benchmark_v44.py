import copy
import json
import unittest
from unittest.mock import patch
from ops.tests.test_research_unified_cohort_v43 import cohort
from ops.research_unified_market_benchmark_v44 import run,compare,losses

def fixture():
    kw=cohort()
    kw["train_cutoff"]="2026-11-27T07:59:00Z"
    return kw

class BenchmarkV44Tests(unittest.TestCase):
    def check(self,kw,ok=True):
        r=run(**kw)
        self.assertIs(r["structural_review_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("source_authenticity_verified","external_timestamp_verified",
                  "independent_oos_proven","certified_ev","model_promotion_allowed"):
            self.assertIs(r[k],False)
        self.assertEqual(len(r["missing_release_evidence"]),6)
        if not ok:
            self.assertNotIn("benchmark",r)
            self.assertFalse(r["market_comparison_performed"])
        return r
    def test_matched_market(self):
        kw=fixture()
        r=self.check(kw)
        self.assertTrue(r["market_comparison_performed"])
        self.assertEqual(r["benchmark"]["n"],1)
        self.assertEqual(r["benchmark"]["days"],1)
        self.assertIsNone(r["benchmark"]["descriptive_cluster_ci95"])
        self.assertEqual(r["excluded_prematch_outside_test_window"],0)
        args=kw["executions"][0]["live_cases"]["synthetic"]["inputs"]
        p=json.loads(args["prematch_raw"])
        inv={k:1/v for k,v in p["snapshots"][0]["odds"].items()}
        probs={k:v/sum(inv.values()) for k,v in inv.items()}
        obs=kw["finals"]["synthetic"]["final_observations"][0]
        y="home" if obs["home"]>obs["away"] else "away" if obs["home"]<obs["away"] else "draw"
        self.assertEqual(r["benchmark"]["market"],losses(probs,y))
        self.assertEqual(r,self.check(copy.deepcopy(kw)))
    def test_pre_cutoff_prior_excluded(self):
        r=self.check(cohort())
        self.assertFalse(r["market_comparison_performed"])
        self.assertEqual(r["excluded_prematch_outside_test_window"],1)
        self.assertEqual(r["benchmark"]["n"],0)
        self.assertIsNone(r["benchmark"]["model_minus_market"])
    def test_invalid_final(self):
        kw=fixture()
        kw["finals"]["synthetic"]["final_observations"][1]["home"]=30
        self.check(kw,False)
    def test_duplicate_fixture(self):
        kw=fixture();kw["executions"]*=2
        self.check(kw,False)
    def test_invalid_receipt(self):
        kw=fixture()
        kw["executions"][0]["live_cases"]["synthetic"]["inputs"]["prematch_receipt"]["status"]="READY"
        self.check(kw,False)
    def test_no_unverified_release(self):
        kw=fixture()
        with patch("ops.research_unified_market_benchmark_v44.review",
                   return_value={"structural_review_passed":True,"status":"READY",
                                 "production_recommendations":"ENABLED"}):
            self.check(kw,False)
    def test_cluster_thresholds_and_determinism(self):
        rows=[{"day":str(i%20),"model":{"brier":.3,"log_loss":.6},
               "market":{"brier":.4,"log_loss":.7}} for i in range(100)]
        self.assertIsNone(compare(rows[:-1])["descriptive_cluster_ci95"])
        result=compare(rows)
        self.assertEqual(result,compare(rows))
        self.assertAlmostEqual(result["model_minus_market"]["brier"],-.1)
        for interval in result["descriptive_cluster_ci95"].values():
            self.assertAlmostEqual(interval[0],-.1)
            self.assertAlmostEqual(interval[1],-.1)
    def test_insufficient_days(self):
        rows=[{"day":"same","model":{"brier":.3,"log_loss":.6},
               "market":{"brier":.4,"log_loss":.7}} for _ in range(100)]
        self.assertIsNone(compare(rows)["descriptive_cluster_ci95"])

if __name__=="__main__":unittest.main()
