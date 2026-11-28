import unittest
from pathlib import Path
from unittest.mock import patch
from ops.research_forecast_batch_v22 import batch,MAX_RUNS

def loc():
    return {"cases":[{"key":"a","state":"MATCHING_PROOF_INPUT_CANDIDATE",
       "proof_candidates":[{"archive_run":p,"case_id":"c","pair_index":0} for p in ("one","two")]}]}
def result(raw,root,path):
    return {"archive_run":path,"state":"VERIFIED","cases":[{"key":"a","case_id":"c","pair_index":0,
        "observed_before_recorded_kickoff":True}]}
class BatchTests(unittest.TestCase):
    def test_dedupe(self):
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=result):
            r=batch(b"test",Path("."),loc())
        self.assertEqual(r["unique_witness_before_recorded_kickoff_count"],1)
        self.assertEqual(r["run_states"],{"VERIFIED":2})
        self.assertTrue(r["batch_passed"])
        self.assertEqual(r["authenticated_samples"],0)
    def test_failed_run(self):
        def fail(raw,root,path):
            return {"archive_run":path,"state":"AUDIT_REJECTED","cases":[]} if path=="one" else result(raw,root,path)
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=fail):
            r=batch(b"test",Path("."),loc())
        self.assertFalse(r["batch_passed"])
        self.assertEqual(r["unique_witness_before_recorded_kickoff_count"],1)
    def test_missing_link(self):
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=lambda raw,root,path:{"archive_run":path,"state":"VERIFIED","cases":[]}):
            r=batch(b"test",Path("."),loc())
        self.assertEqual(r["run_states"],{"LINK_RECONCILIATION_REJECTED":2})
        self.assertFalse(r["batch_passed"])
    def test_late_witness(self):
        def late(raw,root,path):
            r=result(raw,root,path);r["cases"][0]["observed_before_recorded_kickoff"]=False;return r
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=late):
            r=batch(b"test",Path("."),loc())
        self.assertEqual(r["unique_witness_before_recorded_kickoff_count"],0)
        self.assertFalse(r["batch_passed"])
    def test_budget(self):
        d=loc();d["cases"][0]["proof_candidates"]=[{"archive_run":str(i),"case_id":"c","pair_index":0} for i in range(17)]
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=result):
            r=batch(b"test",Path("."),d)
        self.assertEqual(MAX_RUNS,17)
        self.assertEqual(r["attempted_runs"],17)
        self.assertEqual(r["unattempted_runs"],0)
        self.assertEqual(r["unattempted_archive_runs"],[])
        self.assertTrue(r["batch_passed"])

