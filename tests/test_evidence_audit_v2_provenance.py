import unittest
from scripts.evidence_audit_v2_provenance import review

def sample():
    return {
        "key": "fixture1",
        "kickoff_utc": "2026-10-14T18:00:00+00:00",
        "forecast_utc": "2026-10-14T10:00:00+00:00",
        "market_utc": "2026-10-14T09:00:00+00:00",
        "y": 0, "p": [0.5, 0.3, 0.2], "m": [0.4, 0.3, 0.3],
        "production_recommendations": "DISABLED",
        "fixture_result_source_independently_verified": True,
    }

class ProvenanceTests(unittest.TestCase):
    def test_flag_alone_is_not_verified(self):
        result = review({"samples": [sample()]}, [])
        self.assertEqual(result["strict_verified_count"], 0)
        self.assertTrue(result["provenance_and_history_issues"])

    def test_two_documented_sources(self):
        row = sample()
        row["result_sources"] = [
            {"upstream_id": provider, "url": "https://example.org/" + provider,
             "captured_utc": "2026-10-14T20:00:00+00:00"}
            for provider in ("sourceA", "sourceB")
        ]
        self.assertEqual(review({"samples": [row]}, [])["strict_verified_count"], 1)

    def test_duplicate_provider_rejected(self):
        row = sample()
        source = {"upstream_id": "same", "url": "https://example.org/result",
                  "captured_utc": "2026-10-14T20:00:00+00:00"}
        row["result_sources"] = [source, source]
        self.assertEqual(review({"samples": [row]}, [])["strict_verified_count"], 0)

    def test_missing_direction_history_flagged(self):
        result = review({"samples": [sample()]})
        self.assertTrue(any("history" in issue["issue"] for issue in result["provenance_and_history_issues"]))

if __name__ == "__main__":
    unittest.main()
