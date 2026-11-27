import copy
import unittest
from unittest.mock import patch
from ops.tests.test_research_unified_market_evidence_v42 import fixture
from ops.tests.test_research_live_evidence_v3 import final,FIN
from ops.research_unified_cohort_v43 import run

def cohort():
    kw,_=fixture()
    return dict(expected_ids=["synthetic"],executions=[kw],
                finals={"synthetic":{"final_observations":final(),"settled_at":FIN}},
                model_release="synthetic",train_start="2026-11-26T00:00:00Z",
                train_cutoff="2026-11-27T09:00:00Z",
                test_end="2026-11-27T10:00:00Z",as_of=FIN)

class UnifiedCohortV43Tests(unittest.TestCase):
    def check(self,kw,ok):
        r=run(**kw)
        self.assertIs(r["structural_review_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("source_authenticity_verified","external_timestamp_verified",
                  "cohort_completeness_proven","independent_oos_proven","certified_ev",
                  "model_promotion_allowed","cross_path_1x2_quote_equality_verified"):
            self.assertIs(r[k],False)
        self.assertIs(r["shared_engine_probability_consistency_verified"],ok)
        if not ok:
            self.assertNotIn("cohort_review",r)
            self.assertNotIn("local_review_sha256",r)
        return r
    def test_end_to_end(self):
        kw=cohort()
        r=self.check(kw,True)
        self.assertEqual(r["declared_fixture_count"],1)
        self.assertLessEqual(r["max_probability_difference"],1e-10)
        self.assertEqual(r["cohort_review"]["test_n"],1)
        self.assertEqual(r["cohort_review"]["train_n"],0)
        self.assertFalse(r["cohort_review"]["weights_fitted"])
        self.assertEqual(r,self.check(copy.deepcopy(kw),True))
    def test_missing_final(self):
        kw=cohort();kw["finals"]={}
        self.check(kw,False)
    def test_missing_expected_fixture(self):
        kw=cohort()
        kw["expected_ids"].append("other")
        kw["finals"]["other"]=copy.deepcopy(kw["finals"]["synthetic"])
        self.check(kw,False)
    def test_duplicate_execution(self):
        kw=cohort();kw["executions"]*=2
        self.check(kw,False)
    def test_duplicate_roster(self):
        kw=cohort();kw["expected_ids"]*=2
        self.check(kw,False)
    def test_receipt_tamper(self):
        kw=cohort()
        kw["executions"][0]["live_cases"]["synthetic"]["inputs"]["prematch_receipt"]["status"]="READY"
        self.check(kw,False)
    def test_conflicting_final(self):
        kw=cohort()
        kw["finals"]["synthetic"]["final_observations"][1]["home"]=3
        self.check(kw,False)
    def test_mixed_release(self):
        kw=cohort();kw["model_release"]="other"
        self.check(kw,False)
    def test_shared_engine_disagreement(self):
        kw=cohort()
        with patch("ops.research_unified_cohort_v43.unified_research_pricing",
                   return_value={"one_x_two":{"home":1.0,"draw":0.0,"away":0.0}}):
            self.check(kw,False)
    def test_unavailable_training_result(self):
        kw=cohort();kw["train_cutoff"]="2026-11-27T09:30:00Z"
        r=self.check(kw,True)
        self.assertEqual(r["cohort_review"]["train_n"],0)
        self.assertEqual(r["cohort_review"]["test_n"],0)
        self.assertFalse(r["cohort_review"]["weights_fitted"])

if __name__=="__main__":unittest.main()
