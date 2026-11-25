"""Four-writer local Git archive -> REAL iPhone builders, with 105+ legacy rows.

Only the original checked-in RESEARCH settlement history is used; all newly
appended rows and four archive batches are synthetic and unauthenticated.
No GitHub write, no Pages publish, no live odds, no official FT verification.
"""

from copy import deepcopy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import unittest

from ops.isolated_settlement_bridge import BridgeHold, reconcile
from ops.mobile_shared_settlement import _assemble, _hash_canonical
from ops.mobile_settlement_parity_preflight import CutoverHold
from ops.tests.test_four_writer_shared_archive_canary import (
    FourWriterSharedArchiveCanaryTests, git,
)


class FourWriterMobileReadParityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.case = FourWriterSharedArchiveCanaryTests(
            "test_all_four_writers_commit_15_exact_gzip_blobs_to_one_archive")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

        # Checked-in research-only history is the baseline; source flags
        # remain explicitly unverified. Never write the checked-in file.
        self.original_path = self.root / "evidence/settled.json"
        self.original_raw = self.original_path.read_bytes()
        self.legacy = json.loads(self.original_raw)
        self.assertGreaterEqual(self.legacy["n"], 105)
        self.assertFalse(self.legacy["results_independently_verified"])
        self.assertEqual(self.legacy["production_recommendations"], "DISABLED")
        self.original_count = self.legacy["n"]
        self.case.legacy.write_bytes(self.original_raw)
        self.case.legacy_bytes = self.original_raw

        synthetic = deepcopy(self.legacy["samples"][0])
        synthetic["key"] = "synthetic/four-writer-mobile-parity/no-real-score"
        synthetic["fixture_result_source_independently_verified"] = False
        synthetic["production_recommendations"] = "DISABLED"
        self.case.incoming.write_text(json.dumps({
            "schema": self.legacy["schema"],
            "checked_utc": self.legacy["checked_utc"],
            "samples": [synthetic],
            "n": 1,
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }, sort_keys=True))
        self.gates = json.loads(
            (self.root / "sources/seven_quality_gates_latest.json").read_text())
        self.market = json.loads((self.root / "market/latest.json").read_text())
        self.now = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
        self.case.provision()

    def integrated_snapshot(self):
        receipts = self.case.append_all(("ndr", "forecast", "openliga", "settlement"))
        self.assertEqual(sum(x["new_files"] for x in receipts.values()), 15)
        sha = self.case.full_readback()
        merged, receipt = reconcile(self.case.legacy, self.case.reader, sha)
        return sha, merged, receipt

    def test_real_105_plus_legacy_and_four_archives_share_one_mobile_input(self):
        sha, merged, receipt = self.integrated_snapshot()
        preview = _assemble(self.legacy, merged, receipt, self.gates,
                            self.market, now=self.now)
        self.assertEqual(receipt["archive_batches"], 1)
        self.assertEqual(receipt["new_samples"], 1)
        self.assertEqual(receipt["legacy_samples"], self.original_count)
        self.assertEqual(receipt["combined_samples"], self.original_count + 1)
        self.assertEqual(preview["legacy_samples"], self.original_count)
        self.assertEqual(preview["official_readiness_samples"],
                         self.original_count + 1)
        self.assertEqual(preview["daily_scorecard_samples"],
                         self.original_count + 1)
        self.assertEqual(preview["canonical_settlement_sha256"],
                         _hash_canonical(merged))
        self.assertEqual(preview["archive_head_sha"], sha)
        self.assertTrue(preview["candidate_same_input_count_parity"])
        self.assertTrue(preview["current_workflow_source_split_detected"])
        self.assertFalse(preview["archive_ref_checked"])
        self.assertFalse(preview["archive_ref_independently_attested"])
        self.assertFalse(preview["verified_final_scores"])
        self.assertFalse(preview["site_published"])
        self.assertFalse(preview["source_switch_authorized"])
        self.assertEqual(preview["production_recommendations"], "DISABLED")
        # The real baseline remains on disk unmodified; same local branch
        # carries other three non-settlement namespaces without polluting it.
        names = git(self.case.reader, "ls-tree", "-r", "--name-only", sha).splitlines()
        self.assertEqual(len([name for name in names if name.endswith(".gz")]), 15)
        self.assertEqual(sum(p.startswith("settlement_batches/") for p in names), 1)
        self.assertEqual(sum(p.startswith("ndr_capture_provenance/") for p in names), 2)
        self.assertEqual(sum(p.startswith("openliga_capture_provenance/") for p in names), 2)
        self.assertEqual(sum(p.startswith("forecast_provenance/") for p in names), 10)
        self.assertEqual(self.original_path.read_bytes(), self.original_raw)
        self.case.assert_main_unchanged()

    def test_missing_or_changed_historic_row_blocked_after_four_writer_read(self):
        _, merged, receipt = self.integrated_snapshot()
        dropped = deepcopy(merged)
        dropped["samples"].pop(0)
        dropped["n"] = len(dropped["samples"])
        with self.assertRaisesRegex(CutoverHold,
                                    "HISTORIC_SETTLEMENT_SAMPLE_MISSING"):
            _assemble(self.legacy, dropped, receipt, self.gates,
                      self.market, now=self.now)
        mutated = deepcopy(merged)
        mutated["samples"][0]["y"] = (mutated["samples"][0]["y"] + 1) % 3
        with self.assertRaisesRegex(CutoverHold,
                                    "HISTORIC_SETTLEMENT_SAMPLE_MUTATED"):
            _assemble(self.legacy, mutated, receipt, self.gates,
                      self.market, now=self.now)
        self.assertEqual(self.original_path.read_bytes(), self.original_raw)
        self.case.assert_main_unchanged()

    def test_tampered_checked_out_batch_rejected_even_with_same_pinned_head(self):
        sha, _, _ = self.integrated_snapshot()
        batch = (self.case.reader / "settlement_batches/2026/11/23/9002-1.json.gz")
        batch.write_bytes(batch.read_bytes() + b"x")
        with self.assertRaisesRegex(BridgeHold, "UNPINNED_ARCHIVE_BLOB"):
            reconcile(self.case.legacy, self.case.reader, sha)
        self.assertEqual(self.original_path.read_bytes(), self.original_raw)
        self.case.assert_main_unchanged()

    def test_untracked_extra_settlement_batch_rejected_not_counted(self):
        sha, _, _ = self.integrated_snapshot()
        extra = (self.case.reader / "settlement_batches/2026/11/23/9009-1.json.gz")
        extra.write_bytes(gzip.compress(self.case.incoming.read_bytes(), mtime=0))
        with self.assertRaisesRegex(BridgeHold, "UNPINNED_ARCHIVE_BLOB"):
            reconcile(self.case.legacy, self.case.reader, sha)
        self.assertEqual(self.original_path.read_bytes(), self.original_raw)
        self.case.assert_main_unchanged()

    def test_main_source_updates_do_not_leak_into_pinned_mobile_archive(self):
        # Simulate a separate, existing main-only producer after the local
        # isolated branch has been provisioned at the older baseline SHA.
        main_update = self.case.writer / "sources/six_league_free_latest.json"
        main_update.parent.mkdir()
        main_update.write_text('{"synthetic_main_drift":true}\n')
        git(self.case.writer, "add", "sources")
        git(self.case.writer, "-c", "user.name=offline-fixture",
            "-c", "user.email=offline@example.org", "commit",
            "-m", "Synthetic producer main update after isolated bootstrap")
        git(self.case.writer, "push", "origin", "HEAD:refs/heads/main")
        newer_main = self.case.remote_head("refs/heads/main")
        self.assertNotEqual(newer_main, self.case.baseline)
        sha, merged, receipt = self.integrated_snapshot()
        self.assertNotEqual(sha, newer_main)
        names = git(self.case.reader, "ls-tree", "-r", "--name-only", sha)
        self.assertNotIn("six_league_free_latest.json", names)
        self.assertEqual(git(self.case.writer, "merge-base", sha, newer_main),
                         self.case.baseline)
        preview = _assemble(self.legacy, merged, receipt, self.gates,
                            self.market, now=self.now)
        self.assertEqual(preview["daily_scorecard_samples"],
                         self.original_count + 1)
        self.assertEqual(preview["official_readiness_samples"],
                         self.original_count + 1)
        self.assertFalse(preview["source_switch_authorized"])
        self.assertEqual(preview["production_recommendations"], "DISABLED")
        self.assertEqual(self.case.remote_head("refs/heads/main"), newer_main)
        self.assertEqual(self.original_path.read_bytes(), self.original_raw)


if __name__ == "__main__":
    unittest.main()
