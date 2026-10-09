"""Duplicate sealed evidence may never inflate independent results agreement."""
import json
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from independent_results import compare

class DuplicateEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        kickoff=self.now-timedelta(hours=5)
        self.sample={"key":json.dumps(["bundesliga","fckoln","bayern",kickoff.isoformat()]),
                     "league":"bundesliga","kickoff_utc":kickoff.isoformat(),
                     "y":2,"production_recommendations":"DISABLED"}
        self.events=[
            {"provider":"thesportsdb","league":"bundesliga","home":"FC Köln",
             "away":"Bayern","kickoff_utc":kickoff.isoformat(),
             "status":"FINISHED","score_ft":[0,2]},
            {"provider":"football_data_org","league":"bundesliga","home":"FC Köln",
             "away":"Bayern","kickoff_utc":kickoff.isoformat(),
             "status":"FINISHED","score_ft":[0,2]}]

    def run_audit(self,samples):
        evidence={"n":len(samples),"samples":samples,
                  "production_recommendations":"DISABLED"}
        sources={"sampled_fixtures":self.events}
        with patch("independent_results.verify",return_value=self.now):
            return compare(evidence,sources,now=self.now)

    def test_single_verified_candidate_agrees(self):
        result=self.run_audit([self.sample])
        self.assertEqual(result["two_provider_agreements"],1)
        self.assertEqual(result["duplicate_evidence_samples"],0)
        self.assertEqual(result["unique_evidence_keys_count"],1)
        self.assertFalse(result["can_unlock_betting"])

    def test_identical_evidence_rows_all_quarantined(self):
        result=self.run_audit([self.sample,dict(self.sample)])
        self.assertEqual(result["two_provider_agreements"],0)
        self.assertEqual(result["single_source_agreements"],0)
        self.assertEqual(result["duplicate_evidence_samples"],2)
        self.assertEqual(result["unmatched_samples"],2)
        self.assertEqual(result["unique_evidence_keys_count"],0)
        self.assertFalse(result["can_unlock_betting"])

    def test_conflicting_claimed_outcome_also_quarantined(self):
        other=dict(self.sample,y=0)
        result=self.run_audit([self.sample,other])
        self.assertEqual(result["two_provider_agreements"],0)
        self.assertEqual(result["duplicate_evidence_samples"],2)

    def test_malformed_evidence_does_not_crash(self):
        result=self.run_audit([{"key":[],"league":"bundesliga"}])
        self.assertEqual(result["unmatched_samples"],1)
        self.assertEqual(result["two_provider_agreements"],0)

if __name__=="__main__":
    unittest.main()
