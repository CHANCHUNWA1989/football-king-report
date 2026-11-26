"""Deterministic adversarial stress checks for football research admission."""
import copy
import hashlib
import json
import random
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from offline_pinned_preflight import validate_pinned_forecast_rows
from offline_walkforward import evaluate_walkforward
from offline_calibration_report import evaluate_binary_calibration
from offline_capture_manifest import assess_pinned_capture_manifest


class TestAdversarialStress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cls.rows = []
        for i in range(180):
            kickoff = base + timedelta(days=i)
            cls.rows.append({
                "event_id": "fixture-" + str(i), "model_version": "v1",
                "predicted_at_utc": (kickoff - timedelta(hours=2)).isoformat(),
                "kickoff_at_utc": kickoff.isoformat(),
                "settled_at_utc": (kickoff + timedelta(hours=3)).isoformat(),
                "probability": 0.6, "outcome": i % 2,
            })

    def test_250_mutations_rejected_before_walkforward(self):
        rng = random.Random(20261024)
        for i in range(250):
            rows = copy.deepcopy(self.rows)
            pos = rng.randrange(1, len(rows))
            kind = i % 5
            if kind == 0:
                rows[pos]["probability"] = float("nan")
            elif kind == 1:
                rows[pos]["predicted_at_utc"] = rows[pos]["kickoff_at_utc"]
            elif kind == 2:
                rows[pos]["settled_at_utc"] = rows[pos]["kickoff_at_utc"]
            elif kind == 3:
                rows[pos]["event_id"] = " " + rows[0]["event_id"] + " "
            else:
                rows[pos]["outcome"] = True
            with self.subTest(iteration=i, mutation=kind):
                self.assertEqual(
                    validate_pinned_forecast_rows(rows, expected_model_version="v1")["status"],
                    "HOLD")

    def test_120_kickoff_boundary_capture_mutations_rejected(self):
        rng = random.Random(424242)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captures.json"
            for i in range(120):
                captures = [
                    {"event_id": row["event_id"],
                     "captured_at_utc": row["predicted_at_utc"],
                     "evidence_source": "synthetic-stress-test"}
                    for row in self.rows
                ]
                pos = rng.randrange(len(captures))
                captures[pos]["captured_at_utc"] = self.rows[pos]["kickoff_at_utc"]
                document = {"schema_version": 1, "history_sha256": "a" * 64,
                            "captures": captures}
                raw = json.dumps(document, sort_keys=True).encode()
                path.write_bytes(raw)
                with self.subTest(iteration=i):
                    result = assess_pinned_capture_manifest(
                        self.rows, manifest_path=path,
                        expected_manifest_sha256=hashlib.sha256(raw).hexdigest(),
                        history_sha256="a" * 64)
                    self.assertEqual(result["status"], "HOLD")
                    self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_100_walkforward_invalid_timing_mutations_rejected(self):
        rng = random.Random(12345)
        for i in range(100):
            rows = copy.deepcopy(self.rows)
            pos = rng.randrange(len(rows))
            rows[pos]["predicted_at_utc"] = rows[pos]["settled_at_utc"]
            with self.subTest(iteration=i):
                self.assertEqual(evaluate_walkforward(rows)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
