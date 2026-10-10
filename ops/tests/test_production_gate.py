"""The production gate never auto-unlocks and explains every missing prerequisite."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from production_gate import gate,MIN_SAMPLES


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

    def test_mismatched_sample_count_rejected(self):
        self.evidence["n"]=200
        with self.assertRaisesRegex(ValueError,"SETTLED_SAMPLE_MISMATCH"):
            gate(self.center,self.evidence,self.validation)

    def test_ci_cannot_replace_verified_results(self):
        self.validation["measurements"]={"difference_block_bootstrap_95pct_ci":[.1,.3]}
        x=gate(self.center,self.evidence,self.validation)
        self.assertFalse(x["conditions"]["independent_six_league_result_verification"])
        self.assertFalse(x["conditions"]["independent_manual_research_approval"])
        self.assertEqual(x["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
