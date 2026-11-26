"""Postmatch diagnostics must never upgrade observations to certified evidence."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import forward_fixture_postmatch_diagnostic as m

def docs():
    ko="2026-11-27T19:30:00+00:00"
    p={"league":"bundesliga","home":"SV Werder Bremen","away":"Borussia Mönchengladbach","kickoff_utc":ko,"provider_match_id":83253,"status":"FINISHED_CONFIRMED_BY_SOURCE","score_ft":[2,1]}
    s={"league":"bundesliga","home":"Werder Bremen","away":"Borussia Mönchengladbach","kickoff_utc":ko,"provider":"thesportsdb","provider_event_id":"2508822","status":"FINISHED","score_ft":[2,1]}
    f={"primary_observed_utc":"2026-11-26T01:50:39+00:00","secondary_observed_utc":"2026-11-25T19:40:05+00:00","candidates":[{"league":p["league"],"home":p["home"],"away":p["away"],"kickoff_utc_recorded":ko,"openligadb_match_id":83253,"thesportsdb_event_id":"2508822"}]}
    return f,{"collected_utc":"2026-11-27T22:00:00+00:00","matches":[p]},{"collected_utc":"2026-11-27T22:10:00+00:00","sampled_fixtures":[s]}

class PostmatchTests(unittest.TestCase):
    def run_case(self,f,p,s,now="2026-11-27T23:00:00+00:00"):
        with patch.object(m,"verify_primary"),patch.object(m,"verify_secondary"):
            r=m.compare(f,p,s,m.stamp(now))
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        return r["rows"][0]
    def test_agreement_not_certified(self):
        r=self.run_case(*docs())
        self.assertEqual(r["state"],"TWO_PUBLISHER_SCORE_AGREEMENT_UNVERIFIED")
        self.assertEqual(r["observed_scores"],[[2,1],[2,1]])
        self.assertFalse(r["forecast_witness_verified"])
        self.assertFalse(r["regulation_time_authenticated"])
    def test_score_conflict(self):
        f,p,s=docs();s["sampled_fixtures"][0]["score_ft"]=[1,2]
        self.assertEqual(self.run_case(f,p,s)["state"],"SCORE_CONFLICT")
    def test_missing_and_duplicate(self):
        f,p,s=docs();s["sampled_fixtures"]=[]
        self.assertEqual(self.run_case(f,p,s)["state"],"MISSING_SOURCE_ROW")
        f,p,s=docs();s["sampled_fixtures"].append(copy.deepcopy(s["sampled_fixtures"][0]))
        self.assertEqual(self.run_case(f,p,s)["state"],"AMBIGUOUS_ID")
    def test_identity_conflict(self):
        f,p,s=docs();s["sampled_fixtures"][0]["kickoff_utc"]="2026-11-27T19:31:00+00:00"
        self.assertEqual(self.run_case(f,p,s)["state"],"IDENTITY_OR_KICKOFF_CONFLICT")
    def test_early_capture(self):
        f,p,s=docs();s["collected_utc"]="2026-11-27T21:29:59+00:00"
        self.assertEqual(self.run_case(f,p,s)["state"],"AWAITING_POSTMATCH_CAPTURE")
    def test_no_final(self):
        f,p,s=docs();s["sampled_fixtures"][0].update(status="SCHEDULED",score_ft=None)
        self.assertEqual(self.run_case(f,p,s)["state"],"AWAITING_BOTH_FINAL_SCORES")
    def test_before_kickoff(self):
        f,p,s=docs();p["collected_utc"]=s["collected_utc"]="2026-11-27T18:00:00+00:00"
        self.assertEqual(self.run_case(f,p,s,now="2026-11-27T18:01:00+00:00")["state"],"AWAITING_RECORDED_KICKOFF_PLUS_2H")
    def test_future_or_regression(self):
        f,p,s=docs();s["collected_utc"]="2026-11-28T01:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"FUTURE_CAPTURE"):self.run_case(f,p,s)
        f,p,s=docs();s["collected_utc"]="2026-11-25T19:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"CAPTURE_REGRESSION"):self.run_case(f,p,s)
