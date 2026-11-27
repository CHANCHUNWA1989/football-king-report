import hashlib
import json
import unittest
from ops.tests.test_research_candidate_gap_v6 import data
from ops.research_evidence_overlap_v23 import join

def fixture():
    d=data();r=d["samples"][0];raw=json.dumps(d).encode();sha=hashlib.sha256(raw).hexdigest()
    result=dict(ledger_sha256=sha,cases=[dict(key=r["key"],league=r["league"],
        state="TWO_PUBLISHER_SCORE_AGREEMENT",authenticated=False)])
    proof=dict(ledger_sha256=sha,witness_keys=[r["key"]],unique_witness_before_recorded_kickoff_count=1,batch_passed=True)
    return raw,result,proof
class OverlapTests(unittest.TestCase):
    def test_overlap(self):
        r=join(*fixture())
        self.assertEqual(r["witness_and_two_publisher_exact_score"],1)
        self.assertEqual(r["witness_and_result_corroboration"],1)
        self.assertEqual(r["authenticated_samples"],0)
    def test_wrong_ledger(self):
        raw,r,p=fixture();p["ledger_sha256"]="0"*64
        with self.assertRaises(ValueError):join(raw,r,p)
    def test_duplicate_witness(self):
        raw,r,p=fixture();p["witness_keys"]*=2
        with self.assertRaises(ValueError):join(raw,r,p)
    def test_conflict_is_not_agreement(self):
        raw,r,p=fixture();r["cases"][0]["state"]="CONFLICT_REVIEW"
        self.assertEqual(join(raw,r,p)["witness_and_result_corroboration"],0)
    def test_missing_case(self):
        raw,r,p=fixture();r["cases"]=[]
        with self.assertRaises(ValueError):join(raw,r,p)
    def test_no_witness(self):
        raw,r,p=fixture();p.update(witness_keys=[],unique_witness_before_recorded_kickoff_count=0,batch_passed=False)
        x=join(raw,r,p);self.assertEqual(x["witness_and_two_publisher_exact_score"],0)
        self.assertFalse(x["forecast_batch_passed"])
