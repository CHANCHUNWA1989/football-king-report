import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recommendation_readiness_gate import evaluate


class ReadinessGateTests(unittest.TestCase):
    def test_missing_evidence_holds(self):
        report = evaluate({})
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(len(report["unmet_requirements"]), 5)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_truthy_strings_are_not_evidence(self):
        report = evaluate({"human_approval": "yes",
                           "independent_pre_match_forecasts": 1})
        self.assertFalse(report["checks"]["human_approval"])
        self.assertFalse(report["checks"]["independent_pre_match_forecasts"])

    def test_full_metadata_only_allows_review(self):
        evidence = {
            "verified_complete_three_market_quotes": True,
            "independent_pre_match_forecasts": True,
            "settled_out_of_sample_validation": True,
            "calibration_and_leakage_review": True,
            "human_approval": True,
        }
        report = evaluate(evidence)
        self.assertEqual(report["status"], "EVIDENCE_REVIEW")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([])


if __name__ == "__main__":
    unittest.main()
