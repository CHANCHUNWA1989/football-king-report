import copy
import json
import unittest
from ops.tests.test_research_prematch_live_bridge_v4 import case
from ops.tests.test_research_live_evidence_v3 import final,FIN
from ops.research_unified_cohort_review_v5 import review

def sample():
    return {"link_inputs":case(),"final_observations":final(),"settled_at":FIN}

def run(cases,**kwargs):
    policy=dict(model_release="synthetic",train_start="2026-11-26T00:00:00Z",
                train_cutoff="2026-11-27T09:00:00Z",test_end="2026-11-27T10:00:00Z",as_of=FIN)
    return review(cases,**{**policy,**kwargs})

class CohortReviewTests(unittest.TestCase):
    def check_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        for key in ("certified_ev","source_authenticity_verified","independent_oos_proven",
                    "model_promotion_allowed","cohort_completeness_proven","test_used_for_weight_selection"):
            self.assertIs(r[key],False)
    def test_matched_models_and_small_cohort(self):
        r=run([sample()])
        self.check_hold(r)
        self.assertTrue(r["structural_review_passed"])
        self.assertEqual((r["train_n"],r["test_n"]),(0,1))
        self.assertFalse(r["weights_fitted"])
        d=r["test_diagnostics"]
        self.assertEqual(set(d["all"]["models"]),{"prematch","clock_baseline","dynamic"})
        self.assertEqual(d["red_card"]["n"],0)
        self.assertEqual(d["no_red_card"]["n"],1)
        self.assertEqual(d["comeback"]["n"],1)
        self.assertGreaterEqual(d["comeback"]["brier"],0)
        self.assertEqual(r["calibration_research"]["reason"],"INSUFFICIENT_REPLAYABLE_COHORT")
        self.assertFalse(r["market_comparison_performed"])
    def test_red_card_stratum(self):
        s=sample()
        rows=[json.loads(raw) for raw in s["link_inputs"]["live_raw_captures"]]
        for row in rows:
            if row["kind"]=="score":row["payload"]["home_red"]=1
        s["link_inputs"]["live_raw_captures"]=[json.dumps(row).encode() for row in rows]
        r=run([s])
        self.assertTrue(r["structural_review_passed"])
        self.assertEqual(r["test_diagnostics"]["red_card"]["n"],1)
        self.assertEqual(r["test_diagnostics"]["no_red_card"]["n"],0)
    def test_invalid_cohort_fails_whole_review(self):
        for mode in ("duplicate","conflict","future","release","tampered"):
            s=sample()
            if mode=="duplicate":cases=[s,s]
            else:
                if mode=="conflict":s["final_observations"][1]["home"]=3
                elif mode=="future":s["settled_at"]="2026-11-27T11:00:00Z"
                elif mode=="release":s["link_inputs"]["model_release"]="other"
                else:s["link_inputs"]["prematch_receipt"]["status"]="READY"
                cases=[s]
            r=run(cases)
            self.check_hold(r)
            self.assertFalse(r["structural_review_passed"])
            self.assertNotIn("test_diagnostics",r)
    def test_training_result_not_available(self):
        r=run([sample()],train_cutoff="2026-11-27T09:30:00Z")
        self.check_hold(r)
        self.assertTrue(r["structural_review_passed"])
        self.assertEqual((r["train_n"],r["test_n"]),(0,0))
        self.assertEqual(r["calibration_research"]["excluded"]["TRAIN_RESULT_NOT_AVAILABLE_BEFORE_CUTOFF"],1)
    def test_empty_or_invalid_window(self):
        for r in (run([]),run([sample()],test_end="2026-11-27T11:00:00Z")):
            self.check_hold(r)
            self.assertFalse(r["structural_review_passed"])
    def test_reproducible_receipt(self):
        s=sample()
        self.assertEqual(run([s]),run([copy.deepcopy(s)]))
        x=run([s])
        for obs in s["final_observations"]:obs["away"]=2
        y=run([s])
        self.assertTrue(y["structural_review_passed"])
        self.assertNotEqual(x["cohort_sha256"],y["cohort_sha256"])
if __name__=="__main__":
    unittest.main()
