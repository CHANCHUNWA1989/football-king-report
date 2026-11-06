import unittest
from ops.audit_existing_1x2_evidence import audit


def sample():
    return {
        "production_recommendations": "DISABLED",
        "results_independently_verified": False,
        "samples": [{
            "key": "match-1", "league": "epl",
            "market_utc": "2026-11-01T10:00:00Z",
            "forecast_utc": "2026-11-01T11:00:00Z",
            "kickoff_utc": "2026-11-01T15:00:00Z",
            "y": 0, "p": [0.6, 0.2, 0.2], "m": [0.5, 0.25, 0.25],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }]
    }


class ExistingEvidenceAuditTests(unittest.TestCase):
    def test_scores_are_research_only(self):
        result = audit(sample())
        self.assertEqual(result["valid_rows"], 1)
        self.assertEqual(result["missing_model_artifact_hash_rows"], 1)
        self.assertEqual(result["missing_result_source_rows"], 1)
        self.assertEqual(result["kickoff_date_range"], ["2026-11-01", "2026-11-01"])
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["profitability_verified"])
        self.assertFalse(result["all_outcomes_independently_verified"])
        self.assertAlmostEqual(result["score_summary_unverified"]["model_brier"], 0.24)

    def test_future_forecast_excluded(self):
        data = sample()
        data["samples"][0]["forecast_utc"] = "2026-11-01T16:00:00Z"
        self.assertEqual(audit(data)["valid_rows"], 0)

    def test_duplicate_key_excluded(self):
        data = sample()
        data["samples"].append(dict(data["samples"][0]))
        self.assertEqual(audit(data)["excluded_rows"], 1)

    def test_unverified_header_never_promotes_outcomes(self):
        data = sample()
        data["results_independently_verified"] = True
        self.assertFalse(audit(data)["all_outcomes_independently_verified"])

    def test_unsafe_archive_rejected(self):
        data = sample()
        data["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            audit(data)

    def test_invalid_probability_excluded(self):
        data = sample()
        data["samples"][0]["p"] = [0.9, 0.9, 0.9]
        self.assertEqual(audit(data)["valid_rows"], 0)


if __name__ == "__main__":
    unittest.main()
