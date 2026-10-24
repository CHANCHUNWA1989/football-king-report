"""Readiness gate must never enable betting from user-supplied assertions."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from production_readiness_gate import REQUIRED, assess_production_readiness


class TestProductionReadinessGate(unittest.TestCase):
    def test_empty_is_hold(self):
        result = assess_production_readiness({})
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["missing_evidence"], list(REQUIRED))
        self.assertIsNone(result["completion_percentage"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_truthy_values_are_not_verification(self):
        result = assess_production_readiness({
            name: "true" for name in REQUIRED
        })
        self.assertEqual(result["status"], "HOLD")

    def test_one_missing_condition_holds(self):
        result = assess_production_readiness({
            name: True for name in REQUIRED[:-1]
        })
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["missing_evidence"], [REQUIRED[-1]])

    def test_even_all_claims_need_external_audit(self):
        result = assess_production_readiness({
            name: True for name in REQUIRED
        })
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertTrue(result["external_audit_required"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_non_dictionary_holds(self):
        self.assertEqual(assess_production_readiness([])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
