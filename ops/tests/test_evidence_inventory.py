"""Evidence inventory must not treat references as proof of readiness."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evidence_inventory import CHECKS, evidence_inventory


class TestEvidenceInventory(unittest.TestCase):
    def test_empty_inventory_exposes_six_missing_evidence_domains(self):
        report = evidence_inventory()
        self.assertEqual(len(report["checks"]), 6)
        self.assertEqual(set(x["id"] for x in report["checks"]), set(CHECKS))
        self.assertTrue(all(x["status"] == "MISSING" for x in report["checks"]))
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["verified_completion_percentage"])

    def test_artifact_references_never_admit_production(self):
        report = evidence_inventory({
            key: {"artifact_reference": "unverified://test"}
            for key in CHECKS
        })
        self.assertTrue(all(x["status"] == "NEEDS_INDEPENDENT_AUDIT"
                            for x in report["checks"]))
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_truthy_claims_do_not_count_as_artifacts(self):
        report = evidence_inventory({key: True for key in CHECKS})
        self.assertTrue(all(x["status"] == "MISSING" for x in report["checks"]))


if __name__ == "__main__":
    unittest.main()
