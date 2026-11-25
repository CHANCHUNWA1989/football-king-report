"""Synthetic post-match tests; no source calls or prospective credit."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_series_replay import case, KO, resign
from vnext_native_postmatch import postmatch

def results():
    a=dict(fixture_id="openligadb:123",origin="result-A",kickoff_utc=KO,
        completed_utc="2026-11-03T21:50:00Z",observed_utc="2026-11-03T21:50:10Z",
        received_utc="2026-11-03T21:50:20Z",scope="FULL_MATCH_REGULATION",
        status="FINISHED",home=0,away=2)
    return [a,dict(a,origin="result-B")]

def run(raw,digest,cuts,r):
    return postmatch(raw,digest,fixture_id="openligadb:123",
        home_native_id="10",away_native_id="20",kickoff_utc=KO,cuts=cuts,
        results=r,as_of_utc="2026-11-03T22:00:00Z")

class PostmatchTests(unittest.TestCase):
    def test_all_cuts_scored_and_one_fixture_not_certified(self):
        raw,digest,cuts=case()
        out=run(raw,digest,cuts,results())
        self.assertEqual(out["postmatch_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertEqual(out["fixture_count"],1)
        self.assertEqual(out["cut_count"],2)
        self.assertEqual(out["verified_forward_sample_credit"],0)
        self.assertFalse(out["final_result_authenticated"])
        self.assertIsNone(out["realized_roi"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        for c in out["cuts"]:
            self.assertEqual(c["actual_1x2"],"AWAY")
            self.assertEqual(c["settlement_grade"],"HALF_LOSS")
            self.assertTrue(0<=c["brier_1x2"]<=2)
            self.assertTrue(0<=c["brier_market"]<=2)
    def test_conflicting_result_and_duplicate_origin(self):
        raw,digest,cuts=case()
        for change in ({"home":1},{"origin":"RESULT-A"}):
            r=results();r[1].update(change)
            out=run(raw,digest,cuts,r)
            self.assertEqual(out["reason"],"FINAL_RESULT_CONFLICT")
            self.assertNotIn("cuts",out)
    def test_final_scope_and_clock_rejected(self):
        raw,digest,cuts=case()
        for change,reason in (({"scope":"EXTRA_TIME"},"INVALID_FINAL_RESULTS"),
            ({"status":"LIVE"},"INVALID_FINAL_RESULTS"),
            ({"completed_utc":"2026-11-03T21:00:00Z"},"FINAL_RESULT_CLOCK_ORDER"),
            ({"received_utc":"2026-11-03T22:01:00Z"},"FINAL_RESULT_CLOCK_ORDER")):
            r=results();r[1].update(change)
            self.assertEqual(run(raw,digest,cuts,r)["reason"],reason)
    def test_final_score_rollback_held(self):
        raw,digest,cuts=case()
        r=results()
        for x in r:x["away"]=1
        self.assertEqual(run(raw,digest,cuts,r)["reason"],"FINAL_SCORE_CORRECTION_REVIEW")
    def test_kickoff_mismatch_and_tamper_fail_closed(self):
        raw,digest,cuts=case()
        c=copy.deepcopy(cuts);c[0]["envelope"]["model"]["kickoff_utc"]="2026-11-03T20:01:00Z"
        resign(c[0])
        self.assertEqual(run(raw,digest,c,results())["reason"],"SERIES_KICKOFF_MISMATCH")
        cuts[1]["snapshot"]["quote"]["decimal_price"]=2.1
        out=run(raw,digest,cuts,results())
        self.assertEqual(out["reason"],"POSTMATCH_SERIES_REJECTED")
        self.assertNotIn("cuts",out)
