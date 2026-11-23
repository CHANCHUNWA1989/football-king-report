"""Research-only cutover inventory; tests must not mutate main/remote Git."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ops.archive_cutover_preflight import CutoverAuditHold, inspect, inspect_file


MINIMAL = """name: synthetic
jobs:
  archive_provenance:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - run: |
          git -C "$proof_worktree" push origin HEAD:refs/heads/main
  archive:
    permissions:
      contents: write
    steps:
      - run: |
          git -C "$worktree" push origin HEAD:refs/heads/main
          gh api -X PUT "repos/$GITHUB_REPOSITORY/contents/evidence/settled.json"
"""


class ArchiveCutoverPreflightTests(unittest.TestCase):
    def test_two_direct_main_writers_and_settlement_put_are_blocked(self):
        r = inspect(MINIMAL)
        self.assertEqual(r["status"], "HOLD_LEGACY_MAIN_WRITERS_PRESENT")
        self.assertEqual(r["legacy_direct_main_push_jobs"],
                         ["archive", "archive_provenance"])
        self.assertEqual(r["legacy_settled_contents_put_jobs"], ["archive"])
        self.assertEqual(r["contents_write_permission_jobs"],
                         ["archive", "archive_provenance"])
        self.assertFalse(r["ruleset_activation_authorized"])
        self.assertFalse(r["inventory_exhaustive"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_existing_checked_in_workflow_is_still_blocked(self):
        root = Path(__file__).resolve().parents[2]
        r = inspect_file(root / ".github/workflows/football-king-iphone.yml")
        self.assertEqual(r["status"], "HOLD_LEGACY_MAIN_WRITERS_PRESENT")
        self.assertIn("archive_provenance", r["legacy_direct_main_push_jobs"])
        self.assertIn("archive", r["legacy_direct_main_push_jobs"])
        self.assertIn("archive", r["legacy_settled_contents_put_jobs"])
        self.assertEqual(len(r["workflow_sha256"]), 64)
        self.assertFalse(r["downstream_read_parity_verified"])

    def test_even_removed_writers_never_grant_auto_release(self):
        no_writes = MINIMAL.replace(
            'git -C "$proof_worktree" push origin HEAD:refs/heads/main', "true"
        ).replace(
            'git -C "$worktree" push origin HEAD:refs/heads/main', "true"
        ).replace(
            'gh api -X PUT "repos/$GITHUB_REPOSITORY/contents/evidence/settled.json"',
            "true",
        )
        r = inspect(no_writes)
        self.assertEqual(r["status"],
                         "HOLD_MIGRATION_NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(r["legacy_direct_main_push_jobs"], [])
        self.assertEqual(r["legacy_settled_contents_put_jobs"], [])
        self.assertFalse(r["archive_branch_live_canary_verified"])
        self.assertFalse(r["independent_review_verified"])
        self.assertFalse(r["ruleset_activation_authorized"])

    def test_missing_legacy_job_cannot_be_interpreted_as_migrated(self):
        data = """jobs:
  archive_provenance:
    runs-on: ubuntu-latest
"""
        r = inspect(data)
        self.assertEqual(r["status"], "HOLD_REQUIRED_ARCHIVE_JOB_UNVERIFIABLE")
        self.assertEqual(r["required_jobs_not_found"], ["archive"])

    def test_comments_are_not_evidence_of_a_live_writer(self):
        data = """jobs:
  archive_provenance:
    steps:
      # git -C "$proof_worktree" push origin HEAD:refs/heads/main
  archive:
    steps:
      # gh api -X PUT repos/x/contents/evidence/settled.json
"""
        r = inspect(data)
        self.assertEqual(r["legacy_direct_main_push_jobs"], [])
        self.assertEqual(r["legacy_settled_contents_put_jobs"], [])
        self.assertEqual(r["status"],
                         "HOLD_MIGRATION_NOT_INDEPENDENTLY_VERIFIED")

    def test_invalid_or_missing_workflow_is_a_hold(self):
        for value in ("", "name: no-jobs", "jobs:\n"):
            with self.subTest(value=value), self.assertRaises(CutoverAuditHold):
                inspect(value)
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "no.yml"
            with self.assertRaisesRegex(CutoverAuditHold,
                                        "UNSAFE_OR_MISSING_WORKFLOW"):
                inspect_file(missing)
            too_large = Path(temp) / "huge.yml"
            too_large.write_bytes(b"0" * 1_000_001)
            with self.assertRaisesRegex(CutoverAuditHold,
                                        "WORKFLOW_SIZE_UNVERIFIABLE"):
                inspect_file(too_large)

    def test_cli_cannot_exit_success_or_claim_ruleset_authority(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "workflow.yml"
            path.write_text(MINIMAL)
            result = subprocess.run(
                [sys.executable, "-m", "ops.archive_cutover_preflight",
                 "--workflow", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["status"],
                             "HOLD_LEGACY_MAIN_WRITERS_PRESENT")
            self.assertFalse(receipt["ruleset_activation_authorized"])
            self.assertEqual(receipt["production_recommendations"],
                             "DISABLED")


if __name__ == "__main__":
    unittest.main()
