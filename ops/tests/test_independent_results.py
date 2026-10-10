"""Result corroboration may never create bets or retroactively edit samples."""
import json
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from independent_results import compare


class IndependentFinalScoreTests(unittest.TestCase):
    def setUp(self):
        self.t=datetime.now(timezone.utc)
        self.kick=self.t-timedelta(hours=5)
        key=["bundesliga","fckoln","bayern",self.kick.isoformat()]
        self.sample={"key":json.dumps(key),"league":"bundesliga",
                     "kickoff_utc":self.kick.isoformat(),"y":2,
                     "production_recommendations":"DISABLED"}
        self.evidence={"n":1,"samples":[self.sample],"production_recommendations":"DISABLED"}
        self.sources={"sampled_fixtures":[
            {"provider":"thesportsdb","league":"bundesliga","home":"FC Köln",
             "away":"Bayern","kickoff_utc":self.kick.isoformat(),
             "status":"FINISHED","score_ft":[0,2]}]}

    def audit(self):
        with patch("independent_results.verify",return_value=self.t):
            return compare(self.evidence,self.sources,now=self.t)

    def test_one_independent_score_only_partial(self):
        a=self.audit()
        self.assertEqual(a["single_source_agreements"],1)
        self.assertEqual(a["two_provider_agreements"],0)
        self.assertFalse(a["all_six_leagues_verified"])
        self.assertFalse(a["can_unlock_betting"])

    def test_two_distinct_providers_agree(self):
        self.sources["sampled_fixtures"].append(
            {**self.sources["sampled_fixtures"][0],"provider":"football_data_org"})
        a=self.audit()
        self.assertEqual(a["two_provider_agreements"],1)
        self.assertFalse(a["independently_validated_prediction_value"])

    def test_two_publishers_same_outcome_but_different_ft_score_are_not_verified(self):
        self.sources["sampled_fixtures"].append({
            **self.sources["sampled_fixtures"][0], "provider":"football_data_org",
            "score_ft":[1,3]  # Both away wins; final score must still match.
        })
        check=self.audit()
        self.assertEqual(check["two_provider_agreements"],0)
        self.assertEqual(check["two_provider_exact_score_agreements"],0)
        self.assertEqual(check["same_outcome_different_final_score_conflicts"],1)
        self.assertEqual(check["conflicting_observations"],1)
        self.assertFalse(check["can_unlock_betting"])

    def test_same_bookmaker_duplicate_is_not_independent_result_provider(self):
        self.sources["sampled_fixtures"].append(
            dict(self.sources["sampled_fixtures"][0]))
        check=self.audit()
        self.assertEqual(check["single_source_agreements"],1)
        self.assertEqual(check["two_provider_exact_score_agreements"],0)

    def test_two_exact_ft_results_count_once(self):
        self.sources["sampled_fixtures"].append(
            {**self.sources["sampled_fixtures"][0], "provider":"football_data_org"})
        check=self.audit()
        self.assertEqual(check["two_provider_exact_score_agreements"],1)
        self.assertEqual(check["same_outcome_different_final_score_conflicts"],0)
        self.assertFalse(check["independently_validated_prediction_value"])

    def test_conflicting_score_is_quarantined(self):
        self.sources["sampled_fixtures"][0]["score_ft"]=[3,0]
        a=self.audit()
        self.assertEqual(a["conflicting_observations"],1)
        self.assertEqual(a["two_provider_agreements"],0)

    def test_wrong_match_time_excluded(self):
        self.sources["sampled_fixtures"][0]["kickoff_utc"]=(self.kick+timedelta(hours=3)).isoformat()
        self.assertEqual(self.audit()["unmatched_samples"],1)

    def test_wrong_league_excluded(self):
        self.sources["sampled_fixtures"][0]["league"]="epl"
        self.assertEqual(self.audit()["unmatched_samples"],1)

    def test_expired_snapshot_stays_hold(self):
        with patch("independent_results.verify",return_value=self.t-timedelta(hours=50)):
            r=compare(self.evidence,self.sources,now=self.t)
        self.assertEqual(r["status"],"HOLD")

    def test_unsafe_evidence_not_used(self):
        self.evidence["production_recommendations"]="ENABLED"
        self.assertEqual(self.audit()["status"],"HOLD")


    def test_malformed_provider_time_is_skipped_not_fatal(self):
        self.sources["sampled_fixtures"].insert(0, {
            **self.sources["sampled_fixtures"][0], "kickoff_utc": "not-a-time"})
        a=self.audit()
        self.assertEqual(a["single_source_agreements"],1)
        self.assertEqual(a["conflicting_observations"],0)

    def test_missing_provider_time_does_not_crash_audit(self):
        self.sources["sampled_fixtures"][0].pop("kickoff_utc")
        a=self.audit()
        self.assertEqual(a["unmatched_samples"],1)
        self.assertFalse(a["can_unlock_betting"])

if __name__=="__main__":
    unittest.main()
