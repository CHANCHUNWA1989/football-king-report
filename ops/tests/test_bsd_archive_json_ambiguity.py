"""Fail-closed BSD archive guard input parsing, including old mutable archives."""
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bsd_free import collect

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "ops" / "bsd_guard.py"


class BSDArchiveJsonAmbiguityTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.new = collect(now=self.now, token="")
        self.old = collect(now=self.now - timedelta(minutes=2), token="")

    def run_guard(self, new_text, old_text):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            new_path, old_path, decision_path = (
                root / "new.json", root / "old.json", root / "decision.json"
            )
            new_path.write_text(new_text, encoding="utf-8")
            old_path.write_text(old_text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(GUARD),
                 "--input", str(new_path),
                 "--previous", str(old_path),
                 "--decision", str(decision_path)],
                cwd=ROOT, text=True, capture_output=True, timeout=10, check=False
            )
            decision = (
                json.loads(decision_path.read_text(encoding="utf-8"))
                if decision_path.exists() else None
            )
            return result, decision

    def duplicate(self, doc, key, injected_value):
        raw = json.dumps(doc, sort_keys=True)
        needle = json.dumps(key) + ":"
        self.assertEqual(raw.count(needle), 1)
        return raw.replace(
            needle, needle + " " + json.dumps(injected_value) + ", " + needle,
            1
        )

    def test_valid_newer_snapshot_is_allowed(self):
        result, decision = self.run_guard(
            json.dumps(self.new), json.dumps(self.old)
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(decision, {"replace": True})

    def test_duplicate_previous_timestamp_cannot_hide_future_archive(self):
        # Standard json.loads accepts the final (old) timestamp and ignores
        # an earlier contradictory future timestamp in the same object.
        old_text = self.duplicate(
            self.old, "captured_utc", "2099-01-01T00:00:00+00:00"
        )
        result, decision = self.run_guard(json.dumps(self.new), old_text)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIsNone(decision)
        self.assertIn("BSD_DUPLICATE_JSON_FIELD", result.stderr + result.stdout)

    def test_duplicate_new_release_gate_cannot_hide_enabled_value(self):
        new_text = self.duplicate(
            self.new, "production_recommendations", "ENABLED"
        )
        result, decision = self.run_guard(new_text, json.dumps(self.old))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIsNone(decision)
        self.assertIn("BSD_DUPLICATE_JSON_FIELD", result.stderr + result.stdout)

    def test_nonfinite_in_unchecked_metadata_is_rejected(self):
        new_text = json.dumps(self.new)
        previous = '"warnings": ' + json.dumps(self.new["warnings"])
        self.assertIn(previous, new_text)
        new_text = new_text.replace(previous, '"warnings": [NaN]', 1)
        self.assertIn("NaN", new_text)
        result, decision = self.run_guard(new_text, json.dumps(self.old))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIsNone(decision)
        self.assertIn("BSD_NONFINITE_JSON_NUMBER", result.stderr + result.stdout)

    def test_oversized_archived_status_is_rejected_before_decision(self):
        old = dict(self.old)
        old["warnings"] = ["x" * (1024 * 1024)]
        result, decision = self.run_guard(json.dumps(self.new), json.dumps(old))
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIsNone(decision)
        self.assertIn("BSD_RESEARCH_JSON_OVERSIZE", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
