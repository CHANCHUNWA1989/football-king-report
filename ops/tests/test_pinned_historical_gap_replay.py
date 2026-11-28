"""Replay fixed real public archives, without network or ledger writes."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ops.targeted_historical_gap_audit import audit


class PinnedHistoricalGapReplayTests(unittest.TestCase):
    def test_pinned_real_history(self):
        repo = Path(__file__).resolve().parents[2]
        manifest = json.loads((repo / "ops/tests/fixtures/pinned_historical_gap_1112.json").read_text())
        entries = manifest["archives"]
        self.assertEqual(len(entries), 56)
        self.assertEqual(len({e["path"] for e in entries}), 56)
        self.assertEqual(sum(e["size"] for e in entries), 97623)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for item in entries:
                rel = Path(item["path"])
                self.assertFalse(rel.is_absolute() or ".." in rel.parts)
                src = repo / "sources/history" / rel
                self.assertFalse(src.is_symlink())
                raw = src.read_bytes()
                self.assertEqual(len(raw), item["size"])
                git_blob = b"blob " + str(len(raw)).encode() + b"\\0" + raw
                self.assertEqual(hashlib.sha1(git_blob).hexdigest(), item["sha"])
                dst = root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(raw)
            result = audit(manifest["backlog"], root)
            self.assertEqual(result["files_inspected"], 56)
            self.assertEqual(result["valid_files"] + result["rejected_files"], 56)
            self.assertEqual(result["missing_day_directories"], 0)
            self.assertEqual(result["target_count"], 19)
            self.assertEqual(result["observed_unverified_targets"] + result["conflicting_targets"]
                             + result["no_match_targets"], 19)
            self.assertEqual(result["authenticated_samples"], 0)
            self.assertEqual(result["executed_api_queries"], 0)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertIsNone(result["formal_metrics"])
            self.assertTrue(all(t["independently_verified"] is False for t in result["targets"]))
            print("PINNED_HISTORICAL_GAP_REPLAY " + json.dumps(result, sort_keys=True))
