import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import forward_fixture_candidate_replay as m

def docs():
    now="2026-11-26T01:50:39+00:00"
    earlier="2026-11-25T19:40:05+00:00"
    r={"league":"bundesliga","home":"SV Werder Bremen","away":"Borussia Mönchengladbach",
        "kickoff_utc":"2026-11-27T19:30:00+00:00","status":"SCHEDULED","score_ft":None,
        "provider_match_id":83253,"source_id_pair":{"thesportsdb_event_id":"2508822"}}
    s={"league":"bundesliga","home":"Werder Bremen","away":"Borussia Mönchengladbach",
        "kickoff_utc":r["kickoff_utc"],"status":"SCHEDULED","score_ft":None,"provider":"thesportsdb","provider_event_id":"2508822"}
    return {"collected_utc":now,"schedule_crosscheck_time_utc":earlier,
        "source_identity_independently_authenticated":False,"unverified_provider_id_pairs":1,"matches":[r]}, {"collected_utc":earlier,"sampled_fixtures":[s]}

class CandidateReplayTests(unittest.TestCase):
    # Isolate the additional join checks; the workflow separately exercises both real guards.
    def run_audit(self,a,b):
        with patch.object(m,"verify_primary"),patch.object(m,"verify_secondary",return_value=m.stamp(b["collected_utc"])):
            return m.audit(a,b)
    def test_exact_alias(self):
        a,b=docs();r=self.run_audit(a,b)
        self.assertEqual(r["candidate_count"],1)
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertFalse(r["candidates"][0]["forecast_witness_verified"])
    def test_wrong_id(self):
        a,b=docs();b["sampled_fixtures"][0]["provider_event_id"]="999"
        with self.assertRaisesRegex(ValueError,"PAIR_CONFLICT"):self.run_audit(a,b)
    def test_duplicate_candidate(self):
        a,b=docs();b["sampled_fixtures"].append(copy.deepcopy(b["sampled_fixtures"][0]))
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS"):self.run_audit(a,b)
    def test_wrong_kickoff_or_reversed_teams(self):
        for field,value in (("kickoff_utc","2026-11-27T19:31:00+00:00"),("home","Borussia Mönchengladbach")):
            a,b=docs();b["sampled_fixtures"][0][field]=value
            with self.assertRaises(ValueError):self.run_audit(a,b)
    def test_source_clock(self):
        a,b=docs();b["collected_utc"]="2026-11-26T02:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"SOURCE_CLOCK"):self.run_audit(a,b)
    def test_reject_finished(self):
        a,b=docs();a["matches"][0]["status"]="FINISHED_CONFIRMED_BY_SOURCE"
        with self.assertRaisesRegex(ValueError,"NOT_PREMATCH"):self.run_audit(a,b)
    def test_reject_changed_bytes(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"sources/latest.json";p.parent.mkdir();p.write_text("{}")
            with self.assertRaisesRegex(ValueError,"PINNED_BLOB_MISMATCH"):m.read(tmp,"sources/latest.json")
