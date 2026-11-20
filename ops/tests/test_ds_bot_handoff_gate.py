"""Synthetic-only regression for the read-only DS Bot handoff boundary."""
import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "ds_bot_handoff_gate.py"
spec = importlib.util.spec_from_file_location("ds_bot_handoff_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
NOW = datetime(2026, 11, 15, 6, 0, 0, tzinfo=timezone.utc)


def fixture():
    return {
        "schema": "football-king-dsbot-handoff-v1",
        "origin": "ds-bot",
        "run_id": "synthetic-test-1",
        "generated_at_utc": "2026-11-15T05:59:00Z",
        "as_of_utc": "2026-11-15T05:00:00Z",
        "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "observations": [{"role": "fixture_audit", "note": "Synthetic note, not an authenticated source.",
                          "references": ["https://example.org/fixture"]}],
    }


class TestDSBotHandoffGate(unittest.TestCase):
    def assert_rejected(self, data, reason):
        with self.assertRaisesRegex(gate.HandoffRejected, reason):
            gate.validate_handoff(data, now=NOW)

    def test_valid_synthetic_held_without_promotion(self):
        result = gate.validate_handoff(fixture(), now=NOW)
        self.assertEqual("HOLD", result["status"])
        self.assertEqual("DISABLED", result["production_recommendations"])
        self.assertFalse(result["independent_source_authentication"])
        self.assertFalse(result["independent_human_review"])
        self.assertFalse(result["eligible_for_prediction_or_betting"])
        self.assertFalse(result["verified_positive_ev"])
        self.assertEqual(0, result["authenticated_forward_samples"])
        self.assertEqual(1, result["reference_count_unverified"])
        self.assertNotIn("observations", result)

    def test_unknown_fields_cannot_claim_certification(self):
        row = fixture()
        row["certified"] = True
        self.assert_rejected(row, "UNEXPECTED_HANDOFF_FIELDS")

    def test_reject_production_enable(self):
        row = fixture()
        row["production_recommendations"] = "ENABLED"
        self.assert_rejected(row, "UNSAFE_STATUS")

    def test_reject_lookahead(self):
        row = fixture()
        row["as_of_utc"] = "2026-11-15T06:00:00Z"
        self.assert_rejected(row, "FUTURE_OR_LOOKAHEAD_TIMESTAMP")

    def test_reject_stale(self):
        row = fixture()
        row["generated_at_utc"] = "2026-11-13T05:59:00Z"
        row["as_of_utc"] = "2026-11-13T05:00:00Z"
        self.assert_rejected(row, "STALE_HANDOFF")

    def test_reject_naive_timestamp(self):
        row = fixture()
        row["generated_at_utc"] = "2026-11-15T05:59:00"
        self.assert_rejected(row, "UTC_TIMESTAMP_REQUIRED")

    def test_reject_duplicate_role(self):
        row = fixture()
        row["observations"].append(copy.deepcopy(row["observations"][0]))
        self.assert_rejected(row, "INVALID_OR_DUPLICATE_ROLE")

    def test_reject_unexpected_review_claim(self):
        row = fixture()
        row["observations"][0]["authenticated"] = True
        self.assert_rejected(row, "UNEXPECTED_OBSERVATION_FIELDS")

    def test_reject_credentials_in_url(self):
        row = fixture()
        row["observations"][0]["references"] = ["https://user:secret@example.org/fixture"]
        self.assert_rejected(row, "INVALID_REFERENCE_URL")

    def test_reject_query_secret(self):
        row = fixture()
        row["observations"][0]["references"] = ["https://example.org/?api_key=secret"]
        self.assert_rejected(row, "INVALID_REFERENCE_URL")

    def test_reject_duplicate_references(self):
        row = fixture()
        row["observations"][0]["references"] *= 2
        self.assert_rejected(row, "INVALID_REFERENCES")

    def test_reject_oversized_file_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "oversized.json"
            p.write_bytes(b"x" * (gate.MAX_BYTES + 1))
            with self.assertRaisesRegex(gate.HandoffRejected, "INVALID_FILE_SIZE_OR_TYPE"):
                gate.inspect_file(p, now=NOW)
            target = Path(tmp) / "valid.json"
            target.write_text(json.dumps(fixture()), encoding="utf-8")
            link = Path(tmp) / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(gate.HandoffRejected, "SYMLINK_INPUT_DISALLOWED"):
                gate.inspect_file(link, now=NOW)

    def test_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "duplicate.json"
            raw = json.dumps(fixture())
            p.write_text(raw.replace('"origin": "ds-bot",',
                                     '"origin": "ds-bot", "origin": "fake",'),
                         encoding="utf-8")
            with self.assertRaisesRegex(gate.HandoffRejected, "DUPLICATE_JSON_KEY"):
                gate.inspect_file(p, now=NOW)

    def test_reject_malformed_references_types(self):
        for invalid in (None, "https://example.org", [None], [{"url": "https://example.org"}]):
            with self.subTest(invalid=invalid):
                row = fixture()
                row["observations"][0]["references"] = invalid
                self.assert_rejected(row, "INVALID_REFERENCES")

    def test_reject_raw_execution_fields(self):
        row = fixture()
        row["observations"][0]["shell_command"] = "echo hello"
        self.assert_rejected(row, "UNEXPECTED_OBSERVATION_FIELDS")

    def test_repeatable_hash_and_file_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "handoff.json"
            data = fixture()
            p.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(gate.validate_handoff(data, now=NOW), gate.inspect_file(p, now=NOW))


if __name__ == "__main__":
    unittest.main()
