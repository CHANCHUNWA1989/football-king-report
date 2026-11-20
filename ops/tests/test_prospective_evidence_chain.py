import unittest
from ops.prospective_evidence_chain import (
    validate_prospective_chain, payload_sha256, canonical_record_sha256,
)


def record():
    return {
        "event_id": "internal-123", "provider_event_id": "provider-123",
        "model_version": "v1", "market": "h2h", "bookmaker": "example",
        "result_provider": "independent-results",
        "result_provider_event_id": "results-123",
        "model_sha256": "a" * 64, "forecast_payload_sha256": "b" * 64,
        "odds_payload_sha256": "c" * 64, "result_payload_sha256": "d" * 64,
        "forecast_captured_utc": "2026-11-06T09:00:00Z",
        "odds_captured_utc": "2026-11-06T10:00:00Z",
        "kickoff_utc": "2026-11-06T12:00:00Z",
        "result_captured_utc": "2026-11-06T15:00:00Z",
        "forecast_source_commit": "abcdef0123456789",
        "source_result_independently_verified": True,
        "production_recommendations": "DISABLED",
    }


class ProspectiveEvidenceChainTests(unittest.TestCase):
    def test_complete_schema_is_still_hold(self):
        result = validate_prospective_chain(record())
        self.assertTrue(result["valid_evidence_chain"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_model_hash_fails(self):
        data = record()
        data.pop("model_sha256")
        self.assertFalse(validate_prospective_chain(data)["valid_evidence_chain"])

    def test_unverified_result_fails(self):
        data = record()
        data["source_result_independently_verified"] = False
        self.assertIn("RESULT_NOT_INDEPENDENTLY_VERIFIED",
                      validate_prospective_chain(data)["reasons"])

    def test_post_kickoff_forecast_fails(self):
        data = record()
        data["forecast_captured_utc"] = "2026-11-06T13:00:00Z"
        self.assertFalse(validate_prospective_chain(data)["valid_evidence_chain"])

    def test_naive_timestamp_fails(self):
        data = record()
        data["odds_captured_utc"] = "2026-11-06T10:00:00"
        self.assertFalse(validate_prospective_chain(data)["valid_evidence_chain"])

    def test_recommendations_never_enabled(self):
        data = record()
        data["production_recommendations"] = "ENABLED"
        self.assertFalse(validate_prospective_chain(data)["valid_evidence_chain"])

    def test_payload_hash_requires_raw_bytes(self):
        self.assertEqual(len(payload_sha256(b"raw")), 64)
        with self.assertRaises(TypeError):
            payload_sha256("raw")

    def test_canonical_hash_independent_of_key_order(self):
        self.assertEqual(canonical_record_sha256({"a": 1, "b": 2}),
                         canonical_record_sha256({"b": 2, "a": 1}))


if __name__ == "__main__":
    unittest.main()
