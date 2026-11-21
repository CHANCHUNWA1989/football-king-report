import unittest
from ops.private_soccerdata_research_cli import run


def record(i, day, outcome):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T12:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "outcome": outcome}


class ResearchCliTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"schema": "football-king-soccerdata-research-input-v1",
                        "min_train": 2, "test_days": 1,
                        "records": [record(1, "2026-01-01", "H"),
                                    record(2, "2026-01-01", "D"),
                                    record(3, "2026-01-02", "A")]}

    def test_actual_report_and_manifest(self):
        result = run(self.payload)
        self.assertEqual(result["baseline"]["prediction_count"], 1)
        self.assertEqual(len(result["manifest"]["source_records_sha256"]), 64)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertNotIn("predictions", result["baseline"])

    def test_repeated_runs_identical(self):
        self.assertEqual(run(self.payload), run(self.payload))

    def test_wrong_schema_rejected(self):
        self.payload["schema"] = "untrusted"
        with self.assertRaisesRegex(ValueError, "INVALID_RESEARCH_SCHEMA"):
            run(self.payload)

    def test_future_claim_rejected(self):
        self.payload["records"][0]["kickoff_time_verified"] = True
        with self.assertRaises(ValueError):
            run(self.payload)


if __name__ == "__main__":
    unittest.main()
