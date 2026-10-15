import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unified_evidence_manifest import manifest


def fixtures():
    return (
        [{"fixture_id": '["epl","A","B","2026-10-16"]', "production_recommendations": "DISABLED"}],
        [{"event_id": "model1", "independently_verified": False, "production_recommendations": "DISABLED"}],
        {"status": "HOLD", "accepted": 0, "production_recommendations": "DISABLED"},
        {"independently_verified_settlements": 0, "required_independent_settlements": 300,
         "ready_for_production": False, "production_recommendations": "DISABLED", "blockers": ["NO_RESULTS"]},
    )


class UnifiedEvidenceManifestTests(unittest.TestCase):
    def test_distinct_forecast_types_not_settlements(self):
        data = manifest(*fixtures())
        self.assertEqual(data["four_model_sealed_fixture_count"], 1)
        self.assertEqual(data["poisson_archived_forecast_count"], 1)
        self.assertEqual(data["remaining_independent_settlements"], 300)
        self.assertEqual(data["status"], "HOLD")
        self.assertFalse(data["ready_for_production"])

    def test_duplicate_archive_refused(self):
        sealed, model, score, readiness = fixtures()
        with self.assertRaises(ValueError):
            manifest(sealed * 2, model, score, readiness)

    def test_fake_model_verification_refused(self):
        sealed, model, score, readiness = fixtures()
        model[0]["independently_verified"] = True
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness)

    def test_production_promotion_refused(self):
        sealed, model, score, readiness = fixtures()
        readiness["ready_for_production"] = True
        with self.assertRaises(ValueError):
            manifest(sealed, model, score, readiness)


if __name__ == "__main__":
    unittest.main()
