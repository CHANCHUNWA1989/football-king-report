import unittest
from ops.result_verification_audit import audit_results

class AuditTests(unittest.TestCase):
    def test_empty_audit_stays_disabled(self):
        result = audit_results([], [])
        self.assertEqual(result["verified_count"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_independent_sources(self):
        fixtures = [{"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        row = {"fixture_id":"f1","provider_id":"a","independent_group_id":"upstream-a","status":"FT",
               "published_utc":"2026-10-10T15:00:00Z","home_goals":2,"away_goals":1}
        result = audit_results(fixtures, [row, dict(row, provider_id="b", independent_group_id="upstream-b")])
        self.assertEqual(result["verified_count"], 1)

    def test_duplicate_fixture_rejected(self):
        row = {"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}
        with self.assertRaises(ValueError):
            audit_results([row,row], [])

    def test_missing_independence_provenance_is_hold(self):
        fixture = [{"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        row = {"fixture_id":"f1","provider_id":"a","status":"FT",
               "published_utc":"2026-10-10T15:00:00Z","home_goals":2,"away_goals":1}
        result = audit_results(fixture, [row, dict(row, provider_id="b")])
        self.assertEqual(result["verified_count"], 0)

    def test_mirrored_upstream_not_independent(self):
        fixture = [{"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        row = {"fixture_id":"f1","provider_id":"a","independent_group_id":"feed-1",
               "status":"FT","published_utc":"2026-10-10T15:00:00Z",
               "home_goals":2,"away_goals":1}
        result = audit_results(fixture, [row, dict(row, provider_id="b")])
        self.assertEqual(result["verified_count"], 0)

    def test_unrelated_observations_cannot_affect_fixture(self):
        fixture = [{"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}]
        other = {"fixture_id":"unrelated","provider_id":"a","independent_group_id":"feed-a",
                 "status":"FT","published_utc":"2026-10-10T15:00:00Z","home_goals":3,"away_goals":0}
        result = audit_results(fixture, [other, dict(other, provider_id="b", independent_group_id="feed-b")])
        self.assertEqual(result["verified_count"], 0)
        self.assertEqual(result["results"][0]["status"], "HOLD")

    def test_duplicate_fixture_rejected_before_processing_observations(self):
        fixture = {"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}
        with self.assertRaises(ValueError):
            audit_results([fixture, fixture], [{"fixture_id":"f1","independent_group_id":"feed"}])
