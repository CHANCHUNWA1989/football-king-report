"""Pinned history source gate regression tests."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_history_source_gate import load_pinned_history


class TestPinnedHistory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "history.json"
        self.document = {"schema_version": 1, "model_version": "model-v1",
                         "rows": [{"event_id": f"match-{i}", "model_version": "model-v1"}
                                  for i in range(90)]}
        self._write()

    def _write(self):
        raw = json.dumps(self.document, sort_keys=True).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _load(self, **kwargs):
        return load_pinned_history(
            self.path, expected_sha256=kwargs.get("digest", self.digest),
            expected_model_version=kwargs.get("version", "model-v1"))

    def test_matching_pin_is_research_only(self):
        result = self._load()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["row_count"], 90)
        self.assertFalse(result["external_timestamp_verified"])

    def test_tampered_bytes_hold(self):
        self.path.write_bytes(self.path.read_bytes() + b" ")
        self.assertEqual(self._load()["status"], "HOLD")

    def test_wrong_model_version_holds(self):
        self.assertEqual(self._load(version="model-v2")["status"], "HOLD")

    def test_deeply_nested_json_holds(self):
        raw = ("[" * 2000 + "0" + "]" * 2000).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self._load()["status"], "HOLD")

    def test_invalid_utf8_holds(self):
        raw = b"\\xff\\xfe"
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()
        self.assertEqual(self._load()["status"], "HOLD")

    def test_oversized_history_holds(self):
        with self.path.open("wb") as stream:
            stream.truncate(20_000_001)
        self.assertEqual(self._load()["status"], "HOLD")

    def test_invalid_pin_holds(self):
        self.assertEqual(self._load(digest="bad")["status"], "HOLD")

    def test_mixed_model_rows_hold(self):
        self.document["rows"][0]["model_version"] = "model-v2"
        self._write()
        self.assertEqual(self._load()["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
