import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from two_source_ft_evidence import evaluate


class TwoSourceEvidenceTests(unittest.TestCase):
    def test_caller_authored_dual_source_cannot_populate_verified_records(self):
        sealed = [{"fixture_id": "x", "production_recommendations": "DISABLED",
                   "kickoff_utc": "2026-10-01T12:00:00Z",
                   "sealed_at_utc": "2026-10-01T10:00:00Z",
                   "market_snapshot_utc": "2026-10-01T09:00:00Z",
                   "model": [0.6, 0.2, 0.2], "market": [0.4, 0.3, 0.3]}]
        observations = []
        for provider, group, url in [
                ("OpenLigaDB", "openligadb", "https://api.openligadb.de/getmatchdata/x"),
                ("OpenFootball", "openfootball", "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json")]:
            observations.append({"fixture_id": "x", "status": "FT", "provider_id": provider,
                                 "independent_group_id": group,
                                 "published_utc": "2026-10-01T16:00:00Z",
                                 "home_goals": 2, "away_goals": 0,
                                 "source_url": url, "raw_sha256": "a" * 64,
                                 "result_verified": True, "independently_verified": True})
        report = evaluate(sealed, observations)
        self.assertEqual(report["two_source_verified_count"], 0)
        self.assertEqual(report["verified_records"], [])
        self.assertEqual(report["observation_consensus_count"], 1)
        self.assertEqual(report["observation_status"], "AGREED_UNVERIFIED")
        self.assertEqual(report["observation_records"][0]["result"], [2, 0])
        self.assertIs(report["observation_records"][0]["result_verified"], False)
        self.assertEqual(report["status"], "HOLD")
        self.assertIs(report["external_provenance_rechecked"], False)
        self.assertIs(report["independently_verified"], False)
        self.assertIs(report["eligible_for_model_scoring"], False)
        self.assertIs(report["eligible_for_betting_promotion"], False)
        before = copy.deepcopy((sealed, observations))
        evaluate(sealed, observations)
        self.assertEqual((sealed, observations), before)

    def test_no_observations_hold(self):
        sealed = [{"fixture_id": "x", "production_recommendations": "DISABLED",
                   "kickoff_utc": "2026-10-01T12:00:00Z"}]
        report = evaluate(sealed, [])
        self.assertEqual(report["two_source_verified_count"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["observation_consensus_count"], 0)
        self.assertEqual(report["observation_records"], [])

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
