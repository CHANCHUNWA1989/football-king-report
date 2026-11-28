import json
import unittest
from copy import deepcopy
from ops.tests.test_research_live_intake_v4 import inputs
from ops.tests.test_research_unified_live_v2 import NOW
from ops.tests.test_research_live_evidence_v3 import final,FIN
from ops.research_live_pipeline_v10 import capture,replay,review

def case(probability_only=False):
    rows,policy=inputs()
    if probability_only:rows=[r for r in rows if r["kind"]!="quote"]
    raw=[json.dumps(r).encode() for r in rows]
    receipt=capture(raw,policy,event_id="synthetic",as_of=NOW,
                    model_release="test",probability_only=probability_only)
    return dict(receipt=json.loads(json.dumps(receipt)),raw_captures=raw,policy=policy,
                final_observations=final(),settled_at=FIN)
def run(cases):
    return review(cases,model_release="test",train_start="2026-11-27T00:00:00Z",
                  train_cutoff="2026-11-28T00:00:00Z",test_end="2026-11-29T00:00:00Z",
                  as_of="2026-11-30T00:00:00Z")
class PipelineTests(unittest.TestCase):
    def test_end_to_end_both_modes(self):
        for mode in (False,True):
            r=run([case(mode)])
            self.assertTrue(r["pipeline_replay_passed"])
            self.assertEqual(r["candidate_pairs"],1)
            self.assertEqual(r["probability_review"]["probability_only_count"],int(mode))
            self.assertFalse(r["calibration_research"]["weights_fitted"])
            self.assertEqual(r["authenticated_samples"],0)
            self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_raw_byte_mutation(self):
        c=case();c["raw_captures"][0]+=b" "
        self.assertFalse(run([c])["pipeline_replay_passed"])
    def test_policy_mutation(self):
        c=case();c["policy"]["adapters"]["adapter0"]["source"]="another"
        self.assertFalse(run([c])["pipeline_replay_passed"])
    def test_conflicting_final(self):
        c=case();c["final_observations"][0]["home"]=3
        r=run([c]);self.assertFalse(r["pipeline_replay_passed"])
        self.assertEqual(r["candidate_pairs"],0)
    def test_duplicates(self):
        c=case();self.assertFalse(run([c,deepcopy(c)])["pipeline_replay_passed"])
    def test_receipt_roundtrip(self):
        c=case()
        self.assertEqual(replay(c["receipt"],c["raw_captures"],c["policy"])["event_id"],"synthetic")
    def test_empty(self):
        r=run([]);self.assertTrue(r["pipeline_replay_passed"])
        self.assertEqual(r["candidate_pairs"],0)
        self.assertFalse(r["calibration_research"]["weights_fitted"])
