"""Offline real-Git tests for read-only pinned archive/main drift inventory."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ops.archive_branch_drift_inventory import (
    ArchiveDriftHold, inventory, main,
)


def git(repo, *argv):
    return subprocess.run(
        ["git", "-C", str(repo), *argv], capture_output=True,
        check=True, text=True,
    ).stdout.strip()


class ArchiveBranchDriftInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fk-drift-fixture-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        subprocess.run(
            ["git", "init", str(self.repo)],
            capture_output=True, check=True,
        )
        self.write("README.md", "immutable synthetic baseline\n")
        self.commit("synthetic root")
        git(self.repo, "branch", "-M", "main")
        self.base = git(self.repo, "rev-parse", "HEAD")

    def write(self, path, contents):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents, encoding="utf-8")

    def commit(self, title):
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=offline",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", title)
        return git(self.repo, "rev-parse", "HEAD")

    def test_ahead_main_classifies_exact_history_and_mutable_names(self):
        self.write("forecast_provenance/2026/11/23/123-1/paired.json.gz", "fake")
        self.write("sources/history/2026/11/23/123-1.json.gz", "fake")
        self.write("sources/latest.json", '{"new":true}')
        self.write("market/latest.json", '{"synthetic":true}')
        self.write("README.md", "a code change should not be silently ignored\n")
        new_main = self.commit("simulate 2026-11-23 real main drift")
        receipt = inventory(self.repo, self.base, new_main)
        self.assertEqual(receipt["relationship"], "archive_ancestor_of_main")
        self.assertEqual(receipt["changed_files"], 5)
        self.assertEqual(receipt["historical_added"], 2)
        self.assertEqual(receipt["mutable_publisher_change"], 2)
        self.assertEqual(receipt["unclassified_change"], 1)
        self.assertEqual(receipt["historical_mutated_or_removed"], 0)
        self.assertEqual(receipt["merge_base_sha"], self.base)
        self.assertEqual(len(receipt["path_manifest_sha256"]), 64)
        self.assertFalse(receipt["branch_protection_verified"])
        self.assertFalse(receipt["archive_write_authorized"])
        self.assertFalse(receipt["source_bytes_reconciled"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_immutable_file_change_or_deletion_never_becomes_addition(self):
        self.write("history/2026/11/23/old.json.gz", "old fixture")
        self.write("shadow/2026/11/23/lost.json.gz", "old fixture")
        archive = self.commit("synthetic historical files")
        self.write("history/2026/11/23/old.json.gz", "mutated fixture")
        (self.repo / "shadow/2026/11/23/lost.json.gz").unlink()
        main_sha = self.commit("unexpected rewrite and loss")
        record = inventory(self.repo, archive, main_sha)
        self.assertEqual(record["historical_added"], 0)
        self.assertEqual(record["historical_mutated_or_removed"], 2)
        self.assertEqual(
            {v["git_status"] for v in
             record["files_by_category"]["historical_mutated_or_removed"]},
            {"M", "D"})
        self.assertIn("HOLD", record["status"])

    def test_divergence_does_not_masquerade_as_clean_cutover(self):
        git(self.repo, "checkout", "-b", "research/forward-provenance-archive")
        self.write("settlement_batches/2026/11/23/123-1.json.gz", "fake")
        archive = self.commit("archive has independent evidence")
        git(self.repo, "checkout", "main")
        self.write("sources/latest.json", "new fixture main")
        main_sha = self.commit("main has independent new status")
        record = inventory(self.repo, archive, main_sha)
        self.assertEqual(record["relationship"], "diverged")
        self.assertEqual(record["merge_base_sha"], self.base)
        self.assertEqual(record["historical_mutated_or_removed"], 1)
        self.assertEqual(record["mutable_publisher_change"], 1)
        self.assertFalse(record["archive_write_authorized"])

    def test_same_sha_is_still_hold_not_an_authorization(self):
        r = inventory(self.repo, self.base, self.base)
        self.assertEqual(r["relationship"], "same_commit")
        self.assertEqual(r["changed_files"], 0)
        self.assertFalse(r["actual_remote_head_verified"])
        self.assertFalse(r["independent_review_verified"])
        self.assertIn("HOLD", r["status"])

    def test_invalid_sha_noncommit_and_unrelated_history_fail_closed(self):
        for sha in ("0" * 39, "bad", "../../main", "a" * 40):
            with self.subTest(sha=sha), self.assertRaises(ArchiveDriftHold):
                inventory(self.repo, sha, self.base)
        object_sha = git(self.repo, "hash-object", "README.md")
        with self.assertRaisesRegex(ArchiveDriftHold, "PINNED_OBJECT_NOT_COMMIT"):
            inventory(self.repo, object_sha, self.base)
        with tempfile.TemporaryDirectory() as other:
            unrelated = Path(other)
            subprocess.run(["git", "init", str(unrelated)], check=True,
                           capture_output=True)
            (unrelated / "new.txt").write_text("unrelated")
            git(unrelated, "add", ".")
            git(unrelated, "-c", "user.name=fixture", "-c",
                "user.email=fixture@example.org", "commit", "-m", "unrelated")
            sha = git(unrelated, "rev-parse", "HEAD")
            # Inject the unrelated commit object without any remote network.
            git(self.repo, "fetch", str(unrelated), sha)
            with self.assertRaises(ArchiveDriftHold):
                inventory(self.repo, sha, self.base)

    def test_nonroot_or_missing_path_is_rejected(self):
        (self.repo / "subfolder").mkdir()
        with self.assertRaisesRegex(ArchiveDriftHold, "REPOSITORY_ROOT_MISMATCH"):
            inventory(self.repo / "subfolder", self.base, self.base)
        with self.assertRaisesRegex(ArchiveDriftHold, "INVALID_LOCAL_REPOSITORY"):
            inventory(self.repo / "does-not-exist", self.base, self.base)

    def test_cli_exits_nonzero_even_with_valid_matched_commits(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "--repo", str(self.repo),
                "--archive-sha", self.base,
                "--main-sha", self.base,
            ])
        self.assertEqual(code, 1)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["changed_files"], 0)
        self.assertFalse(receipt["main_ruleset_activation_authorized"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_cli_bad_sha_never_exposes_untrusted_input(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([
                "--repo", str(self.repo),
                "--archive-sha", "private-credential-token",
                "--main-sha", self.base,
            ])
        self.assertEqual(code, 1)
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["status"],
                         "HOLD_DRIFT_INVENTORY_NOT_VERIFIABLE")
        self.assertNotIn("private-credential-token", output.getvalue())
        self.assertFalse(receipt["archive_write_authorized"])

    def test_no_network_or_mutation_git_commands_in_inventory(self):
        # Hook subprocess.run only for inventory itself; git config/commit
        # in fixture setup is intentionally outside the observer.
        calls = []
        real_run = subprocess.run

        def capture(argv, *a, **k):
            calls.append(argv)
            return real_run(argv, *a, **k)

        with mock.patch("ops.archive_branch_drift_inventory.subprocess.run",
                        side_effect=capture):
            inventory(self.repo, self.base, self.base)
        names = [arg[3] for arg in calls]
        self.assertEqual(names, ["rev-parse", "cat-file", "cat-file",
                                 "merge-base", "diff"])
        self.assertFalse({"fetch", "push", "checkout", "reset", "merge"} & set(names))


if __name__ == "__main__":
    unittest.main()
