import unittest
from ops.prematch_evidence_capture import capture_pre_match


def metadata():
    return {
        "event_id": "e-1", "provider_event_id": "p-1",
        "model_version": "v1", "market": "h2h", "bookmaker": "example",
        "forecast_source_commit": "abcdef123",
        "forecast_captured_utc": "2026-11-06T08:00:00Z",
        "odds_captured_utc": "2026-11-06T09:00:00Z",
        "kickoff_utc": "2026-11-06T12:00:00Z",
    }


class PrematchCaptureTests(unittest.TestCase):
    def test_result_not_required_or_stored(self):
        result = capture_pre_match(metadata(), b"f", b"o", b"m")
        self.assertEqual(result["outcome_status"], "NOT_YET_SETTLED")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("result_payload_sha256", result["record"])
        self.assertFalse(result["source_independently_attested"])

    def test_future_forecast_rejected(self):
        m = metadata()
        m["forecast_captured_utc"] = "2026-11-06T13:00:00Z"
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_future_odds_rejected(self):
        m = metadata()
        m["odds_captured_utc"] = "2026-11-06T13:00:00Z"
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_missing_identity_rejected(self):
        m = metadata()
        m.pop("provider_event_id")
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_digest_changes_when_quote_changes(self):
        a = capture_pre_match(metadata(), b"f", b"o", b"m")
        b = capture_pre_match(metadata(), b"f", b"o2", b"m")
        self.assertNotEqual(a["record_sha256"], b["record_sha256"])


if __name__ == "__main__":
    unittest.main()
