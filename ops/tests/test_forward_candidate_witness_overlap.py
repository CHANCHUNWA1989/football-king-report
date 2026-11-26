import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forward_candidate_witness_overlap import join

def rows():
    c={"league":"bundesliga","home":"SV Werder Bremen","away":"Borussia Mönchengladbach","kickoff_utc_recorded":"2026-11-27T19:30:00+00:00","openligadb_match_id":83253,"thesportsdb_event_id":"2508822"}
    r={**c,"home":"Werder Bremen","event_id":"openligadb:83253","source_prediction_utc":"2026-11-25T10:00:00+00:00","candidate_generated_utc":"2026-11-25T10:15:00+00:00","verified_tlog_utc":"2026-11-25T10:24:21+00:00","observed_before_recorded_kickoff":True}
    return c,r
class WitnessOverlapTests(unittest.TestCase):
    def state(self,c,r):
        d=join([c],r)
        self.assertEqual(d["verified_forward_sample_credit"],0)
        self.assertFalse(d["rows"][0]["source_identity_authenticated"])
        return d["rows"][0]["state"]
    def test_native(self):
        c,r=rows();self.assertEqual(self.state(c,[r]),"EXACT_NATIVE_ID_WITNESS_CANDIDATE")
    def test_team_time_only(self):
        c,r=rows();r["event_id"]="other:83253"
        self.assertEqual(self.state(c,[r]),"TEAM_TIME_WITNESS_ONLY")
    def test_wrong_native(self):
        c,r=rows();r["event_id"]="openligadb:83254"
        self.assertEqual(self.state(c,[r]),"NATIVE_ID_FIXTURE_CONFLICT")
    def test_duplicate(self):
        c,r=rows();self.assertEqual(self.state(c,[r,r]),"AMBIGUOUS_FORECAST")
    def test_missing(self):
        c,r=rows();self.assertEqual(self.state(c,[]),"NO_WITNESSED_FORECAST_MATCH")
    def test_clock(self):
        c,r=rows();r["verified_tlog_utc"]="2026-11-27T19:25:00+00:00"
        self.assertEqual(self.state(c,[r]),"WITNESS_CLOCK_REJECTED")
    def test_native_other_fixture(self):
        c,r=rows();r["kickoff_utc_recorded"]="2026-11-27T19:31:00+00:00"
        self.assertEqual(self.state(c,[r]),"NATIVE_ID_FIXTURE_CONFLICT")
