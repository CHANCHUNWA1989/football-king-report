"""Synthetic cohort tests; no real data or source calls."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_series_replay import case, KO
from test_vnext_native_postmatch import results
from vnext_native_cohort import evaluate_cohort, _report

AS_OF="2026-11-03T22:00:00Z"

def fixture():
    raw,digest,cuts=case()
    return dict(raw=raw,archive_sha256=digest,fixture_id="openligadb:123",
        home_native_id="10",away_native_id="20",kickoff_utc=KO,cuts=cuts,results=results())

class CohortTests(unittest.TestCase):
    def test_one_fixture_two_cuts_one_band(self):
        out=evaluate_cohort([fixture()],as_of_utc=AS_OF)
        self.assertEqual(out["cohort_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertEqual(out["fixture_count"],1)
        self.assertEqual(len(out["paired_1x2_groups"]),1)
        g=out["paired_1x2_groups"][0]
        self.assertEqual(g["fixture_count"],1)
        self.assertEqual(g["minute_band"],[45,60])
        self.assertIsNone(g["mean_paired_delta"])
        self.assertEqual(out["paired_market_groups"][0]["fixture_count"],1)
        self.assertEqual(out["verified_forward_sample_credit"],0)
        self.assertFalse(out["weight_updates_applied"])
        self.assertIsNone(out["pooled_accuracy"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
    def test_duplicates_and_bad_case_fail_atomically(self):
        c=fixture()
        out=evaluate_cohort([c,copy.deepcopy(c)],as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"DUPLICATE_COHORT_FIXTURE")
        self.assertNotIn("paired_1x2_groups",out)
        c["cuts"][1]["snapshot"]["quote"]["decimal_price"]=2.1
        out=evaluate_cohort([c],as_of_utc=AS_OF)
        self.assertEqual(out["reason"],"COHORT_CASE_REJECTED")
        self.assertNotIn("paired_market_groups",out)
    def test_descriptive_sample_floor(self):
        self.assertIsNone(_report([{"brier_1x2":.1}]*19,("brier_1x2",))["mean_paired_delta"])
        g=_report([{"brier_1x2":.1}]*20,("brier_1x2",))
        self.assertEqual(g["status"],"DESCRIPTIVE_ONLY")
        self.assertAlmostEqual(g["mean_paired_delta"]["brier_1x2"],.1)
    def test_empty_and_invalid_clock(self):
        self.assertEqual(evaluate_cohort([],as_of_utc=AS_OF)["reason"],"INVALID_COHORT")
        self.assertEqual(evaluate_cohort([fixture()],as_of_utc="bad")["reason"],"INVALID_COHORT")
