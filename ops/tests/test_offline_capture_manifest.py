"""Per-event manifest regression tests."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_capture_manifest import assess_pinned_capture_manifest


class TestCaptureManifest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "manifest.json"
        self.history_digest = "a" * 64
        self.rows = [
            {"event_id": "a", "predicted_at_utc": "2026-01-01T08:00:00Z",
             "kickoff_at_utc": "2026-01-01T12:00:00Z"},
            {"event_id": "b", "predicted_at_utc": "2026-02-01T08:00:00Z",
             "kickoff_at_utc": "2026-02-01T12:00:00Z"},
        ]
        self.manifest = {
            "schema_version": 1, "history_sha256": self.history_digest,
            "captures": [
                {"event_id": "a", "captured_at_utc": "2026-01-01T09:00:00Z",
                 "evidence_source": "external-ledger"},
                {"event_id": "b", "captured_at_utc": "2026-02-01T09:00:00Z",
                 "evidence_source": "external-ledger"},
            ]}
        self._write()

    def _write(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _check(self, digest=None):
        return assess_pinned_capture_manifest(
            self.rows, manifest_path=self.path,
            expected_manifest_sha256=digest or self.digest,
            history_sha256=self.history_digest)

    def test_distinct_event_capture_times(self):
        result = self._check()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["event_count"], 2)
        self.assertFalse(result["timestamp_authority_verified"])

    def test_oversized_manifest_holds(self):
        with self.path.open("wb") as stream:
            stream.truncate(20_000_001)
        self.assertEqual(self._check()["status"], "HOLD")

    def test_tampered_manifest_holds(self):
        self.path.write_bytes(self.path.read_bytes() + b" ")
        self.assertEqual(self._check()["status"], "HOLD")

    def test_missing_event_holds(self):
        self.manifest["captures"][1]["event_id"] = "c"
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_post_kickoff_capture_holds(self):
        self.manifest["captures"][1]["captured_at_utc"] = "2026-02-01T13:00:00Z"
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")

    def test_duplicate_capture_holds(self):
        self.manifest["captures"][1]["event_id"] = "a"
        self._write()
        self.assertEqual(self._check()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
