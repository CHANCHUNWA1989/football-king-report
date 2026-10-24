"""The production gate never auto-unlocks and explains every missing prerequisite."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from production_gate import gate,MIN_SAMPLES


def research_evidence():
    """Valid synthetic research rows, deliberately NOT certified samples."""
    first = datetime(2026, 7, 1, 18, tzinfo=timezone.utc)
    rows = []
    for index in range(300):
        kickoff = first + timedelta(weeks=index % 12)
        rows.append({
            "key": "unverified-research-" + str(index),
            "league": ("epl", "bundesliga", "laliga", "seriea")[index % 4],
            "kickoff_utc": kickoff.isoformat(),
            "forecast_utc": (kickoff - timedelta(hours=1)).isoformat(),
            "market_utc": (kickoff - timedelta(hours=2)).isoformat(),
            "production_recommendations": "DISABLED",
            "fixture_result_source_independently_verified": False,
            "p": [.5, .25, .25], "m": [.45, .3, .25], "y": index % 3,
        })
    return {"schema": "football-king-forward-research-1", "n": len(rows),
            "checked_utc": "2026-10-24T09:40:00Z", "samples": rows,
            "production_recommendations": "DISABLED",
            "results_independently_verified": False, "profitability_verified": False}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.center={"production_recommendations":"DISABLED",
                     "six_league_result_verification_complete":False,
                     "market_odds_are_executable":False,"guaranteed_positive_roi":False}
        self.evidence={"production_recommendations":"DISABLED","samples":[],"n":0}
        self.validation={"production_recommendations":"DISABLED","status":"HOLD",
                         "immutable_forecast_evidence_verified":False,
                         "measurements":None}

    def test_empty_sample_fails_closed(self):
        x=gate(self.center,self.evidence,self.validation)
        self.assertEqual(x["status"],"HOLD")
        self.assertEqual(x["settled_samples"],0)
        self.assertIn("at_least_300_settled_point_in_time_samples",x["failed_conditions"])
        self.assertFalse(x["automated_release_supported"])

    def test_progress_reports_only_actual_settled_evidence(self):
        x = gate(self.center, self.evidence, self.validation)
        progress = x["validation_progress"]
        self.assertEqual(progress["settled_samples"], 0)
        self.assertEqual(progress["additional_samples_needed"], MIN_SAMPLES)
        self.assertEqual(progress["additional_week_blocks_needed"], 12)
        self.assertEqual(progress["independently_verified_result_count"], 0)
        self.assertEqual(set(progress["per_league_settled"]), {
            "epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"})
        self.assertEqual(x["production_recommendations"], "DISABLED")

    def test_unsafe_source_rejected(self):
        self.center["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_FOR_GATE"):
            gate(self.center,self.evidence,self.validation)

    def test_guaranteed_profit_claim_never_unlocks_roi_evidence(self):
        self.center["guaranteed_positive_roi"]=True
        self.validation["measurements"]={
            "difference_block_bootstrap_95pct_ci":[.05,.15]}
        outcome=gate(self.center,self.evidence,self.validation)
        self.assertFalse(outcome["conditions"][
            "positive_risk_adjusted_roi_and_clv_independently_tested"])
        self.assertTrue(outcome["guaranteed_future_roi_is_not_a_qualifying_claim"])
        self.assertEqual(outcome["production_recommendations"],"DISABLED")

    def test_mismatched_sample_count_rejected(self):
        self.evidence["n"]=200
        with self.assertRaisesRegex(ValueError,"SETTLED_SAMPLE_MISMATCH"):
            gate(self.center,self.evidence,self.validation)

    def test_nonempty_forged_sample_rejected_before_qualification(self):
        self.evidence["samples"] = [{
            "league": "epl", "kickoff_utc": "2026-10-10T12:00:00+00:00",
            "production_recommendations": "DISABLED"}]
        self.evidence["n"] = 1
        with self.assertRaises(ValueError):
            gate(self.center, self.evidence, self.validation)

    def test_ci_cannot_replace_verified_results(self):
        self.validation["measurements"]={"difference_block_bootstrap_95pct_ci":[.1,.3]}
        x=gate(self.center,self.evidence,self.validation)
        self.assertFalse(x["conditions"]["independent_six_league_result_verification"])
        self.assertFalse(x["conditions"]["independent_manual_research_approval"])
        self.assertEqual(x["production_recommendations"],"DISABLED")

    def test_valid_300_research_rows_do_not_satisfy_authenticated_qualification(self):
        result = gate(self.center, research_evidence(), self.validation)
        # Preserve real research coverage, without counting it as certification.
        self.assertEqual((result["settled_samples"], result["week_blocks"],
                          result["qualifying_leagues"]), (300, 12, 4))
        for key in ("at_least_300_settled_point_in_time_samples",
                    "at_least_12_independent_week_blocks",
                    "at_least_four_leagues_with_40_completed_samples"):
            self.assertFalse(result["conditions"][key], key)
        self.assertIn("AUTHENTICATED_FORWARD_ADMISSION_NOT_IMPLEMENTED", result["blockers"])
        for progress in (result, result["validation_progress"]):
            self.assertTrue(progress["legacy_counts_are_unverified_research"])
            self.assertEqual(progress["recorded_research_samples"], 300)
            self.assertEqual(progress["recorded_research_week_blocks"], 12)
            self.assertEqual(progress["recorded_research_leagues_with_40"], 4)
            self.assertEqual(progress["authenticated_forward_samples"], 0)
            self.assertEqual(progress["authenticated_week_blocks"], 0)
            self.assertEqual(progress["authenticated_leagues_with_40"], 0)
            self.assertEqual(progress["remaining_authenticated_samples"], 300)
            self.assertEqual(progress["remaining_authenticated_weeks"], 12)
            self.assertEqual(progress["remaining_authenticated_leagues"], 4)
        self.assertEqual(result["validation_progress"]["independently_verified_result_count"], 0)
        progress = result["validation_progress"]
        self.assertEqual(progress["settled_samples"], 0)
        self.assertEqual(progress["additional_samples_needed"], 300)
        self.assertEqual(progress["independent_week_blocks"], 0)
        self.assertEqual(progress["additional_week_blocks_needed"], 12)
        self.assertEqual(progress["leagues_with_at_least_40"], 0)

    def test_caller_attestation_and_aggregate_fields_cannot_qualify_research_rows(self):
        evidence = research_evidence()
        for document in (self.center, evidence, self.validation):
            document.update(authenticated_forward_samples=300,
                            authenticated_week_blocks=12,
                            authenticated_leagues_with_40=4,
                            signature_identity_and_subject_verified=True,
                            external_provenance_rechecked=True,
                            reviewed_by="claimed-independent-reviewer")
        result = gate(self.center, evidence, self.validation)
        self.assertEqual(result["authenticated_forward_samples"], 0)
        self.assertFalse(result["authenticated_forward_admission_implemented"])
        self.assertFalse(result["qualification_counts_authenticated"])
        self.assertEqual(result["remaining_authenticated_samples"], 300)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_true_row_claims_are_rejected_not_counted_as_certified(self):
        evidence = research_evidence()
        for row in evidence["samples"]:
            row["fixture_result_source_independently_verified"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_SETTLEMENT"):
            gate(self.center, evidence, self.validation)


if __name__=="__main__":
    unittest.main()
