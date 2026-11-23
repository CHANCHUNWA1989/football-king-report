"""Synthetic, local-git settlement reader compatibility tests — no remote writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from isolated_settlement_bridge import BridgeHold, reconcile, reconcile_official_remote
from ops.archive_remote_ref_gate import RemoteRefHold


def git(where, *args):
    return subprocess.run(
        ["git", "-C", str(where), *args], capture_output=True, text=True,
        check=True).stdout.strip()


class IsolatedSettlementBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.legacy = root / "legacy-settled.json"
        self.archive = root / "archive"
        self.archive.mkdir()
        git(self.archive, "init")
        self.kickoff = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        self.base_sample = {
            "key": "fixture-one",
            "kickoff_utc": self.kickoff.isoformat(),
            "forecast_utc": (self.kickoff-timedelta(hours=1)).isoformat(),
            "market_utc": (self.kickoff-timedelta(hours=2)).isoformat(),
            "y": 1, "p": [0.4, 0.3, 0.3], "m": [0.3, 0.4, 0.3],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        self.legacy_doc = self.doc([self.base_sample])
        self.legacy.write_text(json.dumps(self.legacy_doc))
        self.legacy_original = self.legacy.read_bytes()

    @staticmethod
    def doc(rows):
        return {
            "schema": "football-king-forward-research-1",
            "checked_utc": "2026-11-26T00:00:00+00:00",
            "samples": rows, "n": len(rows),
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }

    def save_batch(self, raw, run="101", attempt="1", day="2026/11/23"):
        folder = self.archive / "settlement_batches" / day
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (run + "-" + attempt + ".json.gz")
        payload = json.dumps(raw).encode() if isinstance(raw, dict) else raw
        path.write_bytes(gzip.compress(payload, mtime=0))
        return path

    def commit(self):
        git(self.archive, "add", ".")
        git(self.archive, "-c", "user.name=test",
            "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "immutable test batches")
        return git(self.archive, "rev-parse", "HEAD")

    def new_sample(self, key="fixture-two"):
        sample = deepcopy(self.base_sample)
        sample["key"] = key
        return sample

    def test_preserves_old_and_adds_new_without_main_writes(self):
        self.save_batch(self.doc([self.new_sample()]))
        sha = self.commit()
        result, receipt = reconcile(self.legacy, self.archive, sha)
        self.assertEqual(result["n"], 2)
        self.assertEqual(receipt["legacy_samples"], 1)
        self.assertEqual(receipt["combined_samples"], 2)
        self.assertEqual(receipt["new_samples"], 1)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(self.legacy.read_bytes(), self.legacy_original)
        self.assertEqual(git(self.archive, "rev-parse", "HEAD"), sha)

    def test_identical_replay_adds_zero(self):
        self.save_batch(self.legacy_doc)
        sha = self.commit()
        combined, receipt = reconcile(self.legacy, self.archive, sha)
        self.assertEqual(combined["n"], 1)
        self.assertEqual(receipt["new_samples"], 0)

    def test_two_immutable_batches_aggregate(self):
        self.save_batch(self.doc([self.new_sample()]), run="101")
        self.save_batch(self.doc([self.new_sample("fixture-three")]), run="102")
        sha = self.commit()
        combined, receipt = reconcile(self.legacy, self.archive, sha)
        self.assertEqual((combined["n"], receipt["new_samples"],
                          receipt["archive_batches"]), (3, 2, 2))

    def test_changed_same_fixture_outcome_fails_closed(self):
        replaced = self.new_sample("fixture-one")
        replaced["y"] = 0
        self.save_batch(self.doc([replaced]))
        sha = self.commit()
        with self.assertRaisesRegex(ValueError, "CONFLICTING_RESULT"):
            reconcile(self.legacy, self.archive, sha)
        self.assertEqual(self.legacy.read_bytes(), self.legacy_original)

    def test_unsafe_production_label_rejected(self):
        unsafe = self.doc([self.new_sample()])
        unsafe["production_recommendations"] = "ENABLED"
        self.save_batch(unsafe)
        sha = self.commit()
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_SAFETY"):
            reconcile(self.legacy, self.archive, sha)

    def test_real_repository_105_sample_baseline_survives_idempotent_replay(self):
        # The checked-out repository's legacy evidence must remain usable.
        # This is real historical *research* data, NOT independently verified FT.
        root = Path(__file__).resolve().parents[2]
        actual = root / "evidence" / "settled.json"
        original_bytes = actual.read_bytes()
        baseline = json.loads(original_bytes)
        self.assertGreaterEqual(baseline["n"], 105)
        self.assertEqual(baseline["n"], len(baseline["samples"]))
        self.assertIs(baseline["results_independently_verified"], False)
        self.assertIs(baseline["profitability_verified"], False)
        self.assertEqual(baseline["production_recommendations"], "DISABLED")
        self.save_batch(baseline, run="900")
        sha = self.commit()
        merged, receipt = reconcile(actual, self.archive, sha)
        self.assertEqual(merged["n"], baseline["n"])
        self.assertEqual(merged["samples"], baseline["samples"])
        self.assertEqual(receipt["new_samples"], 0)
        self.assertEqual(receipt["legacy_sha256"],
                         __import__("hashlib").sha256(original_bytes).hexdigest())
        self.assertEqual(actual.read_bytes(), original_bytes)

    def test_modified_tracked_batch_rejected_even_if_head_sha_matches(self):
        self.save_batch(self.doc([self.new_sample()]), run="101")
        sha = self.commit()
        # Checked-out bytes have changed WITHOUT a new Git commit.
        self.save_batch(self.doc([self.new_sample("injected")]), run="101")
        self.assertEqual(git(self.archive, "rev-parse", "HEAD"), sha)
        with self.assertRaisesRegex(BridgeHold, "UNPINNED_ARCHIVE_BLOB"):
            reconcile(self.legacy, self.archive, sha)

    def test_untracked_new_batch_rejected_even_if_head_sha_matches(self):
        self.save_batch(self.doc([self.new_sample()]), run="101")
        sha = self.commit()
        # A forged extra run file was not included in the pinned Git tree.
        self.save_batch(self.doc([self.new_sample("untracked")]), run="102")
        self.assertEqual(git(self.archive, "rev-parse", "HEAD"), sha)
        with self.assertRaisesRegex(BridgeHold, "UNPINNED_ARCHIVE_BLOB"):
            reconcile(self.legacy, self.archive, sha)

    def test_gitignored_untracked_batch_cannot_enter_pinned_read(self):
        self.save_batch(self.doc([self.new_sample()]), run="101")
        (self.archive / ".gitignore").write_text(
            "settlement_batches/**/102-1.json.gz\n")
        sha = self.commit()
        # Git status would consider this clean, so we must compare each blob
        # to the actual pinned commit rather than relying on status only.
        self.save_batch(self.doc([self.new_sample("ignored")]), run="102")
        self.assertEqual(git(self.archive, "status", "--porcelain"), "")
        with self.assertRaisesRegex(BridgeHold, "UNPINNED_ARCHIVE_BLOB"):
            reconcile(self.legacy, self.archive, sha)

    def test_official_remote_read_rejects_local_sha_without_git_origin(self):
        self.save_batch(self.doc([self.new_sample()]))
        sha = self.commit()
        # Even a clean, matching local Git tree is NOT proof of the expected
        # GitHub repository/ref. The ordinary offline reader still works.
        local_doc, receipt = reconcile(self.legacy, self.archive, sha)
        self.assertEqual(local_doc["n"], 2)
        self.assertFalse(receipt["remote_ref_checked"])
        with self.assertRaisesRegex(
                RemoteRefHold, "ARCHIVE_REMOTE_IDENTITY_NOT_VERIFIED"):
            reconcile_official_remote(self.legacy, self.archive, sha)

    def test_missing_archive_batch_is_hold(self):
        sha = self.commit()
        with self.assertRaisesRegex(BridgeHold, "MISSING_ISOLATED_SETTLEMENT_ARCHIVE"):
            reconcile(self.legacy, self.archive, sha)

    def test_wrong_archive_checkout_sha_is_hold(self):
        self.save_batch(self.doc([self.new_sample()]))
        self.commit()
        with self.assertRaisesRegex(BridgeHold, "ARCHIVE_HEAD_SHA_MISMATCH"):
            reconcile(self.legacy, self.archive, "0"*40)

    def test_extra_archive_path_is_rejected(self):
        self.save_batch(self.doc([self.new_sample()]))
        forbidden = self.archive / "settlement_batches" / "untrusted.json"
        forbidden.write_text("{}")
        sha = self.commit()
        with self.assertRaisesRegex(BridgeHold, "UNEXPECTED_SETTLEMENT_ARCHIVE_PATH"):
            reconcile(self.legacy, self.archive, sha)

    def test_archive_symlink_is_rejected(self):
        self.save_batch(self.doc([self.new_sample()]))
        forbidden = self.archive / "settlement_batches" / "shortcut"
        forbidden.symlink_to(self.legacy)
        sha = self.commit()
        with self.assertRaisesRegex(BridgeHold, "SYMLINK_IN_SETTLEMENT_ARCHIVE"):
            reconcile(self.legacy, self.archive, sha)

    def test_duplicate_json_key_is_rejected(self):
        self.save_batch(b'{"schema":"x","schema":"x"}')
        sha = self.commit()
        with self.assertRaisesRegex(BridgeHold, "DUPLICATE_JSON_KEY"):
            reconcile(self.legacy, self.archive, sha)

    def test_gzip_bomb_is_rejected_by_decompressed_bound(self):
        self.save_batch(b"z" * 8_000_001)
        sha = self.commit()
        with self.assertRaisesRegex(BridgeHold, "SETTLEMENT_DECOMPRESSED_SIZE_LIMIT"):
            reconcile(self.legacy, self.archive, sha)

    def test_missing_legacy_is_rejected_not_assumed_empty(self):
        self.save_batch(self.doc([self.new_sample()]))
        sha = self.commit()
        self.legacy.unlink()
        with self.assertRaisesRegex(BridgeHold, "UNSAFE_OR_MISSING_SETTLEMENT_FILE"):
            reconcile(self.legacy, self.archive, sha)

    def test_conflicting_repeated_batches_are_rejected(self):
        self.save_batch(self.doc([self.new_sample()]), run="101")
        different = self.new_sample()
        different["y"] = 2
        self.save_batch(self.doc([different]), run="102")
        sha = self.commit()
        with self.assertRaisesRegex(ValueError, "CONFLICTING_RESULT"):
            reconcile(self.legacy, self.archive, sha)


if __name__ == "__main__":
    unittest.main()
