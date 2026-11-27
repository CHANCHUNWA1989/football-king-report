import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from ops.tests.test_research_fusion_witness_v39 import fixture,PINS
from ops.research_fusion_settlement_v40 import settle_candidate

def results():
    a=dict(schema="fusion-final-result-v40",event_id="new-1",league="epl",home="a",away="b",
           kickoff_utc="2026-11-28T15:00:00Z",actual_kickoff_utc="2026-11-28T15:01:00Z",
           finished_utc="2026-11-28T16:55:00Z",observed_utc="2026-11-28T16:56:00Z",
           captured_utc="2026-11-28T16:57:00Z",publisher="publisher-a",upstream="feed-a",
           provider_fixture_id="fixture-a",status="FT",scope="regulation",score=[2,1])
    return [a,dict(deepcopy(a),publisher="publisher-b",upstream="feed-b",provider_fixture_id="fixture-b")]

def run(rows,*,mutate_output=None,returncode=0):
    raw,receipt,bundle,o=fixture()
    if mutate_output:mutate_output(o)
    pins={**PINS,"as_of":"2026-11-28T17:00:00Z"}
    with patch("ops.research_fusion_witness_v39.subprocess.run",return_value=SimpleNamespace(
            returncode=returncode,stdout=json.dumps(o).encode())):
        return settle_candidate(raw,receipt,bundle,[json.dumps(r).encode() for r in rows],**pins)

class FusionSettlementTests(unittest.TestCase):
    def check_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        for k in ("actual_kickoff_authenticated","source_authenticity_verified","upstream_independence_proven",
                  "independent_oos_proven","training_admission","model_promotion_allowed","certified_ev"):
            self.assertIs(r[k],False)
    def test_valid_mocked_witness_and_result(self):
        r=run(results())
        self.check_hold(r)
        self.assertTrue(r["structural_settlement_passed"])
        self.assertEqual(r["final_score"],[2,1])
        self.assertEqual(r["outcome"],"home")
        self.assertEqual(set(r["single_case_descriptive_losses"]),{"market","expanded","fixed_10pct","adaptive_capped"})
        self.assertAlmostEqual(r["single_case_descriptive_losses"]["market"]["brier"],.54)
        self.assertEqual(r["single_case_descriptive_losses"]["market"],r["single_case_descriptive_losses"]["adaptive_capped"])
    def test_result_conflicts(self):
        for field,value in (("score",[1,1]),("actual_kickoff_utc","2026-11-28T15:02:00Z"),
                            ("upstream","FEED-A"),("publisher","PUBLISHER-A"),("event_id","different"),
                            ("home","other"),("scope","extra_time"),("status","LIVE"),
                            ("finished_utc","2026-11-28T16:40:00Z"),("captured_utc","2026-11-28T17:01:00Z")):
            with self.subTest(field=field):
                rows=results();rows[1][field]=value
                r=run(rows);self.check_hold(r)
                self.assertFalse(r["structural_settlement_passed"])
                self.assertNotIn("single_case_descriptive_losses",r)
    def test_both_report_wrong_clock(self):
        rows=results()
        for r in rows:r["actual_kickoff_utc"]="2026-11-28T14:44:00Z"
        self.assertFalse(run(rows)["structural_settlement_passed"])
    def test_witness_failure(self):
        for r in (run(results(),returncode=1),run(results(),mutate_output=lambda o:o[0]["verificationResult"]["statement"]["subject"][0]["digest"].update(sha256="0"*64))):
            self.check_hold(r);self.assertFalse(r["structural_settlement_passed"])
    def test_order_invariant(self):
        rows=results()
        self.assertEqual(run(rows),run(list(reversed(rows))))
    def test_outcomes(self):
        for score,outcome in (([0,0],"draw"),([0,1],"away")):
            rows=results()
            for row in rows:row["score"]=score
            r=run(rows)
            self.assertTrue(r["structural_settlement_passed"])
            self.assertEqual(r["outcome"],outcome)
    def test_missing_result(self):
        self.assertFalse(run(results()[:1])["structural_settlement_passed"])
    def test_invalid_score(self):
        rows=results()
        for r in rows:r["score"]=[True,0]
        self.assertFalse(run(rows)["structural_settlement_passed"])

if __name__=="__main__":
    unittest.main()
