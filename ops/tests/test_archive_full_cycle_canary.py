"""Synthetic full-cycle archive canary in a local bare Git repository only.

Both optional writers share the same pre-provisioned isolated branch. No real
GitHub archive ref, credentials, provider observations or main writes.
Successful test cases must NEVER imply a deployed/attested football feed.
"""

import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.archive_forecast_provenance import FILES
from ops.archive_remote_ref_gate import _verify_fixed_remote
from ops.isolated_provenance_archive import (
    ARCHIVE_REF, ArchiveGateError, append as append_provenance,
)
from ops.isolated_settlement_archive import append as append_settlement
from ops.isolated_settlement_bridge import reconcile


def git(where, *args):
    return subprocess.run(
        ["git", "-C", str(where), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class ArchiveFullCycleCanaryTests(unittest.TestCase):
    """Real local Git push/read round-trip; never uses the GitHub network."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fk-offline-canary-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.remote = root / "remote.git"
        self.clone = root / "writer"
        self.reader = root / "reader"
        self.proof = root / "proof"
        self.legacy = root / "legacy.json"
        self.incoming = root / "incoming.json"
        self.proof.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.clone)],
                       capture_output=True, check=True)
        (self.clone / "README.md").write_text("synthetic main sentinel\n")
        git(self.clone, "add", "README.md")
        git(self.clone, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", "synthetic baseline")
        git(self.clone, "branch", "-M", "main")
        git(self.clone, "push", "origin", "main")
        self.main_sha = self.remote_sha("refs/heads/main")

        for filename in FILES:
            if filename.endswith(".verification.json"):
                data = '[{"ok":true}]'
            elif filename == "negative_checks.json":
                data = json.dumps({"tampered_subject_rejected": True,
                                   "wrong_source_digest_rejected": True})
            elif filename.endswith(".json"):
                data = '{"synthetic_fixture_only":true}'
            else:
                data = "fixture only (not signature evidence)"
            (self.proof / filename).write_text(data)
        self.old_doc = self.document("synthetic-legacy")
        self.new_doc = self.document("synthetic-new")
        self.legacy.write_text(json.dumps(self.old_doc))
        self.incoming.write_text(json.dumps(self.new_doc))
        self.original_legacy_bytes = self.legacy.read_bytes()

    @staticmethod
    def document(key):
        return {
            "schema": "football-king-forward-research-1",
            "checked_utc": "2026-12-02T01:00:00+00:00",
            "samples": [{
                "key": key,
                "kickoff_utc": "2026-12-01T15:00:00+00:00",
                "forecast_utc": "2026-12-01T14:00:00+00:00",
                "market_utc": "2026-12-01T13:00:00+00:00",
                "y": 1,
                "p": [0.4, 0.3, 0.3], "m": [0.3, 0.4, 0.3],
                "fixture_result_source_independently_verified": False,
                "production_recommendations": "DISABLED",
            }],
            "n": 1,
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }

    def remote_sha(self, ref):
        return git(self.clone, "ls-remote", "origin", ref).split()[0]

    def provision_fixture_only(self):
        git(self.clone, "branch", "research/forward-provenance-archive", "main")
        git(self.clone, "push", "origin", ARCHIVE_REF)

    def append_both(self):
        a = append_provenance(
            self.proof, self.clone, "9001", "1", "2026/11/23", max_tries=1)
        b = append_settlement(
            self.incoming, self.legacy, self.clone,
            "9002", "1", "2026/11/23", max_tries=1)
        return a, b

    def assert_main_unchanged(self):
        self.assertEqual(self.remote_sha("refs/heads/main"), self.main_sha)
        self.assertEqual(self.legacy.read_bytes(), self.original_legacy_bytes)

    def test_full_cycle_both_writers_shared_archive_and_pinned_read(self):
        self.provision_fixture_only()
        before_archive = self.remote_sha(ARCHIVE_REF)
        proof, settlement = self.append_both()
        self.assertEqual(proof["status"], "ARCHIVED_ON_ISOLATED_BRANCH")
        self.assertEqual(settlement["status"], "SETTLEMENT_ARCHIVED_RESEARCH_ONLY")
        sha = self.remote_sha(ARCHIVE_REF)
        self.assertNotEqual(sha, before_archive)
        self.assert_main_unchanged()
        paths = git(self.clone, "ls-tree", "-r", "--name-only", sha).splitlines()
        proof_root = "forecast_provenance/2026/11/23/9001-1/"
        self.assertEqual(
            {p for p in paths if p.startswith(proof_root)},
            {proof_root + name + ".gz" for name in FILES})
        self.assertIn("settlement_batches/2026/11/23/9002-1.json.gz", paths)

        subprocess.run(
            ["git", "clone", "--branch", "research/forward-provenance-archive",
             str(self.remote), str(self.reader)],
            check=True, capture_output=True)
        self.assertEqual(git(self.reader, "rev-parse", "HEAD"), sha)
        ref_receipt = _verify_fixed_remote(self.reader, sha, str(self.remote))
        self.assertTrue(ref_receipt["remote_ref_checked"])
        self.assertFalse(ref_receipt["remote_identity_independently_attested"])
        self.assertFalse(ref_receipt["trusted_timestamp_verified"])
        for name in FILES:
            path = self.reader / proof_root / (name + ".gz")
            self.assertEqual(gzip.decompress(path.read_bytes()),
                             (self.proof / name).read_bytes())
        aggregate, receipt = reconcile(self.legacy, self.reader, sha)
        self.assertEqual((aggregate["n"], receipt["new_samples"],
                          receipt["archive_batches"]), (2, 1, 1))
        self.assertEqual(
            {row["key"] for row in aggregate["samples"]},
            {"synthetic-legacy", "synthetic-new"})
        self.assertEqual(receipt["archive_head_sha"], sha)
        self.assertFalse(receipt["results_independently_verified"])
        self.assertFalse(receipt["profitability_verified"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assert_main_unchanged()

    def test_full_cycle_replay_collision_fail_closed_and_preserves_both_refs(self):
        self.provision_fixture_only()
        self.append_both()
        before = self.remote_sha(ARCHIVE_REF)
        proof, settlement = self.append_both()
        self.assertEqual(proof["status"], "ALREADY_ARCHIVED")
        self.assertEqual(settlement["status"], "ALREADY_ARCHIVED")
        self.assertEqual(self.remote_sha(ARCHIVE_REF), before)

        (self.proof / "shadow.json").write_text('{"tampered":true}')
        with self.assertRaisesRegex(ValueError,
                                    "IMMUTABLE_PROVENANCE_ARCHIVE_COLLISION"):
            append_provenance(
                self.proof, self.clone, "9001", "1", "2026/11/23", max_tries=1)
        self.assertEqual(self.remote_sha(ARCHIVE_REF), before)

        # Different original bytes for the same run ID must never overwrite.
        self.incoming.write_text(json.dumps(self.new_doc, indent=2) + "\n")
        with self.assertRaisesRegex(
                ArchiveGateError, "IMMUTABLE_SETTLEMENT_BATCH_COLLISION"):
            append_settlement(
                self.incoming, self.legacy, self.clone,
                "9002", "1", "2026/11/23", max_tries=1)
        self.assertEqual(self.remote_sha(ARCHIVE_REF), before)
        self.assert_main_unchanged()

    def test_unprovisioned_remote_ref_never_falls_back_to_main(self):
        with self.assertRaisesRegex(ArchiveGateError,
                                    "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            append_provenance(
                self.proof, self.clone, "9001", "1", "2026/11/23", max_tries=1)
        with self.assertRaisesRegex(ArchiveGateError,
                                    "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            append_settlement(
                self.incoming, self.legacy, self.clone,
                "9002", "1", "2026/11/23", max_tries=1)
        self.assert_main_unchanged()


if __name__ == "__main__":
    unittest.main()
