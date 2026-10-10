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

    def crosscheck(self):
        from datetime import date
        day = self.kick.date().isoformat()
        return {
            "schema": "football-king-bundesliga-two-publisher-score-candidates-v1",
            "status": "PARTIAL_CHECK",
            "production_recommendations": "DISABLED",
            "sources": ["OpenLigaDB", "OpenFootball"],
            "score_conflicts": 0, "score_comparisons": 1,
            "errors": [], "all_leagues_verified": False,
            "independent_kickoff_verification": False,
            "as_of_utc": self.t.isoformat(),
            "two_publisher_matching_ft_candidate_count": 1,
            "two_publisher_matching_ft_candidates": [{
                "league": "bundesliga", "home": "FC Köln", "away": "Bayern",
                "date_first": day, "date_second": day, "score_ft": [0, 2],
            }],
        }

    def test_public_bundesliga_exact_scores_correlate_only_as_research(self):
        with patch("independent_results.verify", return_value=self.t):
            outcome = compare(self.evidence, self.sources, now=self.t,
                              crosscheck=self.crosscheck())
        check = outcome["bundesliga_two_publisher_candidate_audit"]
        self.assertEqual(check["status"], "CANDIDATE_CORRELATION_ONLY")
        self.assertEqual(check["two_publisher_ft_candidate_fixtures"], 1)
        self.assertEqual(check["settled_outcomes_correlated"], 1)
        self.assertEqual(outcome["two_provider_exact_score_agreements"], 0)
        self.assertFalse(check["results_cryptographically_attested"])
        self.assertFalse(outcome["can_unlock_betting"])

    def test_two_publisher_result_conflict_never_claims_correlation(self):
        cross = self.crosscheck()
        cross["two_publisher_matching_ft_candidates"][0]["score_ft"] = [3, 0]
        with patch("independent_results.verify", return_value=self.t):
            outcome = compare(self.evidence, self.sources, now=self.t,
                              crosscheck=cross)
        check = outcome["bundesliga_two_publisher_candidate_audit"]
        self.assertEqual(check["settled_outcome_conflicts"], 1)
        self.assertEqual(check["settled_outcomes_correlated"], 0)

    def test_tampered_or_old_score_candidate_document_is_held(self):
        for field, bad in (("production_recommendations", "ENABLED"),
                           ("score_conflicts", 1),
                           ("sources", ["ThesportsDB", "OpenLigaDB"]),
                           ("two_publisher_matching_ft_candidate_count", 999),
                           ("as_of_utc", (self.t-timedelta(days=2)).isoformat())):
            with self.subTest(field=field):
                cross = self.crosscheck()
                cross[field] = bad
                with patch("independent_results.verify", return_value=self.t):
                    outcome = compare(self.evidence, self.sources, now=self.t,
                                      crosscheck=cross)
                self.assertEqual(
                    outcome["bundesliga_two_publisher_candidate_audit"]["status"],
                    "HOLD")

    def test_ambiguous_second_match_is_not_assigned_arbitrarily(self):
        cross = self.crosscheck()
        second = dict(cross["two_publisher_matching_ft_candidates"][0])
        second["date_first"] = (self.kick.date()+timedelta(days=1)).isoformat()
        second["date_second"] = second["date_first"]
        cross["two_publisher_matching_ft_candidates"].append(second)
        cross["two_publisher_matching_ft_candidate_count"] = 2
        cross["score_comparisons"] = 2
        with patch("independent_results.verify", return_value=self.t):
            result = compare(self.evidence, self.sources, now=self.t, crosscheck=cross)
        check = result["bundesliga_two_publisher_candidate_audit"]
        self.assertEqual(check["ambiguous_correlations"], 1)
        self.assertEqual(check["settled_outcomes_correlated"], 0)

    def test_correlated_outcome_not_added_to_settlement_ledger(self):
        existing = json.dumps(self.evidence, sort_keys=True)
        with patch("independent_results.verify", return_value=self.t):
            compare(self.evidence, self.sources, now=self.t,
                    crosscheck=self.crosscheck())
        self.assertEqual(json.dumps(self.evidence, sort_keys=True), existing)

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
