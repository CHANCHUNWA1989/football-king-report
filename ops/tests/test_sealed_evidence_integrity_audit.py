"""Synthetic tests for the sealed evidence integrity audit."""
import copy
import unittest
from ops.sealed_evidence_integrity_audit import audit


def fixture():
    return {"key": "fixture-1", "league": "epl",
            "kickoff_utc": "2026-11-08T20:00:00+00:00",
            "forecast_utc": "2026-11-08T18:00:00+00:00",
            "market_utc": "2026-11-08T17:30:00+00:00",
            "y": 0, "p": [.6, .2, .2], "m": [.5, .3, .2],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED"}


def payload(rows):
    return {"schema": "football-king-forward-research-1", "samples": rows}


class IntegrityTests(unittest.TestCase):
    def test_valid_diagnostics_never_certify(self):
        r = audit(payload([fixture()]))
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["unverified_results"], 1)
        self.assertEqual(r["chronologically_valid"], 1)
        self.assertEqual(r["market_within_age_limit"], 1)
        self.assertFalse(r["positive_ev_verified"])

    def test_self_declared_verification_never_certifies(self):
        row = fixture()
        row["fixture_result_source_independently_verified"] = True
        r = audit(payload([row]))
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["independent_provenance_verified"])
        self.assertEqual(r["self_declared_verified_results"], 1)

    def test_stale_market_reported(self):
        row = fixture()
        row["market_utc"] = "2026-11-08T10:00:00+00:00"
        r = audit(payload([row]))
        self.assertEqual(r["stale_market_at_forecast"], 1)

    def test_future_market_detected(self):
        row = fixture()
        row["market_utc"] = "2026-11-08T19:00:00+00:00"
        r = audit(payload([row]))
        self.assertEqual(r["invalid_record_counts"]["lookahead_or_market_after_forecast"], 1)

    def test_duplicate_detected(self):
        row = fixture()
        r = audit(payload([row, copy.deepcopy(row)]))
        self.assertEqual(r["invalid_record_counts"]["duplicate_or_missing_key"], 1)

    def test_invalid_probability_detected(self):
        row = fixture()
        row["p"] = [.9, .9, -.8]
        r = audit(payload([row]))
        self.assertEqual(r["invalid_record_counts"]["invalid_probabilities"], 1)

    def test_unsafe_production_flag_detected(self):
        row = fixture()
        row["production_recommendations"] = "ENABLED"
        r = audit(payload([row]))
        self.assertEqual(r["invalid_record_counts"]["unsafe_production_flag"], 1)

    def test_bad_timestamp_detected(self):
        row = fixture()
        row["forecast_utc"] = "not-a-date"
        r = audit(payload([row]))
        self.assertEqual(r["invalid_record_counts"]["invalid_timestamps"], 1)

    def test_invalid_schema_holds(self):
        self.assertEqual(audit({"samples": []})["reason"], "INVALID_EVIDENCE_SCHEMA")

    def test_bad_age_limit_holds(self):
        self.assertEqual(audit(payload([]), max_market_age_minutes=-1)["reason"],
                         "INVALID_MARKET_AGE_LIMIT")


if __name__ == "__main__":
    unittest.main()
