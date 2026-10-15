import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from two_source_ft_evidence import evaluate


class TwoSourceEvidenceTests(unittest.TestCase):
    def test_no_observations_hold(self):
        sealed = [{"fixture_id": "x", "production_recommendations": "DISABLED",
                   "kickoff_utc": "2026-10-01T12:00:00Z"}]
        report = evaluate(sealed, [])
        self.assertEqual(report["two_source_verified_count"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_untrusted_single_source_cannot_verify(self):
        sealed = [{"fixture_id": "x", "production_recommendations": "DISABLED",
                   "kickoff_utc": "2026-10-01T12:00:00Z"}]
        observations = [{"fixture_id": "x", "status": "FT", "provider_id": "OpenLigaDB",
                         "independent_group_id": "openligadb", "published_utc": "2026-10-01T16:00:00Z",
                         "home_goals": 2, "away_goals": 0,
                         "source_url": "https://api.openligadb.de/getmatchdata/x",
                         "raw_sha256": "a" * 64}]
        self.assertEqual(evaluate(sealed, observations)["two_source_verified_count"], 0)

    def test_unsafe_archive_rejected(self):
        with self.assertRaises(ValueError):
            evaluate([{"fixture_id": "x", "production_recommendations": "ENABLED"}], [])


if __name__ == "__main__":
    unittest.main()
