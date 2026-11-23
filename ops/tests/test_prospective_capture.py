import unittest
from ops.prospective_capture import assemble_capture
from ops.prospective_evidence_chain import payload_sha256, canonical_record_sha256


def metadata():
    return {
        "event_id": "event-1", "provider_event_id": "provider-1",
        "model_version": "v1", "market": "h2h", "bookmaker": "example",
        "result_provider": "independent", "result_provider_event_id": "r-1",
        "forecast_captured_utc": "2026-11-06T08:00:00Z",
        "odds_captured_utc": "2026-11-06T09:00:00Z",
        "kickoff_utc": "2026-11-06T12:00:00Z",
        "result_captured_utc": "2026-11-06T15:00:00Z",
        "forecast_source_commit": "abcdef012345",
        "source_result_independently_verified": False,
    }


class ProspectiveCaptureTests(unittest.TestCase):
    def test_raw_payloads_hashed_without_enabling_recommendations(self):
        c = assemble_capture(metadata(), b"forecast", b"odds", b"result", b"model")
        self.assertEqual(c["record"]["odds_payload_sha256"], payload_sha256(b"odds"))
        self.assertEqual(c["record_sha256"], canonical_record_sha256(c["record"]))
        self.assertEqual(c["status"], "HOLD")
        self.assertEqual(c["production_recommendations"], "DISABLED")
        self.assertFalse(c["validation"]["valid_evidence_chain"])

    def test_modified_raw_odds_changes_digest(self):
        a = assemble_capture(metadata(), b"f", b"odds", b"r", b"m")
        b = assemble_capture(metadata(), b"f", b"odds!", b"r", b"m")
        self.assertNotEqual(a["record_sha256"], b["record_sha256"])

    def test_reject_non_bytes_payload(self):
        with self.assertRaises(TypeError):
            assemble_capture(metadata(), "not-bytes", b"o", b"r", b"m")


if __name__ == "__main__":
    unittest.main()
