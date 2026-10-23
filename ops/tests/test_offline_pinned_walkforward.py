"""Synthetic pinned walk-forward integration tests."""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_pinned_walkforward import replay_pinned_walkforward


class TestPinnedWalkforward(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "history.json"
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = []
        for i in range(180):
            kickoff = base + timedelta(days=i)
            rows.append({
                "event_id": f"match-{i}", "model_version": "v1",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.8, "outcome": 1,
            })
        raw = json.dumps({"schema_version": 1, "model_version": "v1",
                          "rows": rows}, sort_keys=True).encode()
        self.path.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def _run(self, digest=None):
        return replay_pinned_walkforward(
            self.path, expected_sha256=digest or self.digest,
            expected_model_version="v1")

    def test_valid_pin_runs_research_only(self):
        result = self._run()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertGreaterEqual(result["fold_count"], 2)
        self.assertEqual(result["mean_fold_brier"], 0.04)
        self.assertFalse(result["external_timestamp_verified"])
        self.assertFalse(result["model_validated"])

    def test_tamper_holds_before_evaluation(self):
        self.path.write_bytes(self.path.read_bytes() + b" ")
        result = self._run()
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("source_reason", result)

    def test_wrong_pin_holds(self):
        self.assertEqual(self._run("0" * 64)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
