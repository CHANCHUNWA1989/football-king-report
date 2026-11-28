import json
import unittest
from ops.research_candidate_gap_v6 import audit

def data():
    row=dict(key=json.dumps(["epl","a","b","2026-11-01T15:00:00Z"]),league="epl",
             kickoff_utc="2026-11-01T15:00:00Z",forecast_utc="2026-11-01T14:00:00Z",
             market_utc="2026-11-01T07:00:00Z",y=0,p=[.4,.3,.3],m=[.5,.3,.2],
             production_recommendations="DISABLED",fixture_result_source_independently_verified=False)
    return dict(schema="football-king-forward-research-1",production_recommendations="DISABLED",
                results_independently_verified=False,checked_utc="2026-11-02T00:00:00Z",n=1,samples=[row])
def run(d):return audit(json.dumps(d).encode())
class CandidateGapTests(unittest.TestCase):
    def test_candidate(self):
        r=run(data())
        self.assertTrue(r["structural_audit_passed"])
        self.assertEqual(r["candidate_count"],1)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertEqual(r["evidence_gaps"]["MARKET_CAPTURE_OLDER_THAN_6H"],1)
        self.assertEqual(r["evidence_gaps"]["NO_EXACT_SCORE_FIELD"],1)
        self.assertGreater(r["candidate_metrics"]["model_brier"],r["candidate_metrics"]["market_brier"])
    def test_duplicate_offset(self):
        d=data(); row=dict(d["samples"][0])
        row["key"]=json.dumps(["epl","a","b","2026-11-01T23:00:00+08:00"])
        d["samples"].append(row);d["n"]=2
        self.assertFalse(run(d)["structural_audit_passed"])
    def test_leakage(self):
        d=data();d["samples"][0]["forecast_utc"]="2026-11-01T15:00:00Z"
        self.assertFalse(run(d)["structural_audit_passed"])
    def test_self_attested(self):
        d=data();d["samples"][0]["fixture_result_source_independently_verified"]=True
        self.assertFalse(run(d)["structural_audit_passed"])
    def test_bad_vector(self):
        d=data();d["samples"][0]["p"]=[True,0,0]
        self.assertFalse(run(d)["structural_audit_passed"])
    def test_bad_count(self):
        d=data();d["n"]=2
        self.assertFalse(run(d)["structural_audit_passed"])
