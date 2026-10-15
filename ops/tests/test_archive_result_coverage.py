import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive_result_coverage import audit


class CoverageTests(unittest.TestCase):
    def test_missing_results_never_count_as_verified(self):
        report = audit([{"fixture_id": "fixture-1", "production_recommendations": "DISABLED"}], [])
        self.assertEqual(report["missing_result_ids"], 1)
        self.assertEqual(report["independently_attested_settlements"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_claimed_verified_does_not_attest(self):
        report = audit([{"fixture_id": "fixture-1", "production_recommendations": "DISABLED"}],
                       [{"event_id": "fixture-1", "status": "FINAL", "result": "H", "independently_verified": True}])
        self.assertEqual(report["matching_result_ids"], 1)
        self.assertEqual(report["declared_verified_matches_not_audited"], 1)
        self.assertEqual(report["independently_attested_settlements"], 0)

    def test_duplicate_result_rejected(self):
        with self.assertRaises(ValueError):
            audit([], [{"event_id": "x"}, {"event_id": "x"}])

    def test_unsafe_seal_rejected(self):
        with self.assertRaises(ValueError):
            audit([{"fixture_id": "x", "production_recommendations": "ENABLED"}], [])


if __name__ == "__main__":
    unittest.main()
