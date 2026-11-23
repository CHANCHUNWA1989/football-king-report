"""Offline real bare-Git tests for exact remote archive-ref observation.

No GitHub network access or live repository writes. These tests intentionally
use a local filesystem URL only via the private fixture helper; production
entrypoint always requires the pinned GitHub HTTPS origin.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.archive_remote_ref_gate import (
    ARCHIVE_REF, OFFICIAL_ORIGIN, RemoteRefHold,
    _verify_fixed_remote, verify_official_archive_ref,
)


def git(where, *argv):
    p = subprocess.run(["git", "-C", str(where), *argv],
                       capture_output=True, text=True, check=True)
    return p.stdout.strip()


class ArchiveRemoteRefGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "trusted.git"
        self.repo = root / "checkout"
        self.other = root / "other.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(["git", "init", str(self.repo)],
                       capture_output=True, check=True)
        git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "README.md").write_text("main file\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "-c", "user.name=offline",
            "-c", "user.email=offline@example.org",
            "commit", "-m", "baseline")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "origin", "main")
        self.main = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-b", "research/forward-provenance-archive")
        (self.repo / "synthetic-proof.txt").write_text("fixture only\n")
        git(self.repo, "add", "synthetic-proof.txt")
        git(self.repo, "-c", "user.name=offline",
            "-c", "user.email=offline@example.org",
            "commit", "-m", "synthetic archive")
        git(self.repo, "push", "origin", ARCHIVE_REF)
        self.head = git(self.repo, "rev-parse", "HEAD")

    def verify(self, sha=None):
        return _verify_fixed_remote(
            self.repo, self.head if sha is None else sha, str(self.remote))

    def test_correct_remote_fixed_branch_returns_non_release_receipt(self):
        receipt = self.verify()
        self.assertTrue(receipt["remote_ref_checked"])
        self.assertEqual(receipt["archive_ref"], ARCHIVE_REF)
        self.assertEqual(receipt["archive_head_sha"], self.head)
        self.assertFalse(receipt["remote_identity_independently_attested"])
        self.assertFalse(receipt["trusted_timestamp_verified"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_matching_local_head_but_wrong_remote_branch_ref_is_rejected(self):
        # Same commit still exists locally and main is accessible.
        git(self.repo, "push", "origin", "--delete", ARCHIVE_REF)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.head)
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_REMOTE_REF_NOT_CONFIRMED"):
            self.verify()

    def test_remote_moves_after_local_checkout_is_rejected(self):
        git(self.repo, "push", "origin", "--delete", ARCHIVE_REF)
        git(self.repo, "checkout", "main")
        git(self.repo, "checkout", "-b", "other-archive", "main")
        (self.repo / "new.txt").write_text("different remote candidate\n")
        git(self.repo, "add", "new.txt")
        git(self.repo, "-c", "user.name=offline", "-c",
            "user.email=offline@example.org", "commit", "-m", "different")
        git(self.repo, "push", "origin", "HEAD:" + ARCHIVE_REF)
        git(self.repo, "checkout", "--detach", self.head)
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_REMOTE_REF_MISMATCH"):
            self.verify()

    def test_repointed_origin_rejected_even_if_other_remote_has_same_commit(self):
        subprocess.run(["git", "init", "--bare", str(self.other)],
                       capture_output=True, check=True)
        git(self.repo, "push", str(self.other), self.head + ":" + ARCHIVE_REF)
        git(self.repo, "remote", "set-url", "origin", str(self.other))
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_ORIGIN_MISMATCH"):
            self.verify()

    def test_only_main_remote_branch_is_not_sufficient(self):
        git(self.repo, "push", "origin", "--delete", ARCHIVE_REF)
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_REMOTE_REF_NOT_CONFIRMED"):
            self.verify()

    def test_unauthorized_local_origin_cannot_pass_official_fixed_https_gate(self):
        self.assertEqual(OFFICIAL_ORIGIN,
                         "https://github.com/CHANCHUNWA1989/football-king-report.git")
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_ORIGIN_MISMATCH"):
            verify_official_archive_ref(self.repo, self.head)

    def test_missing_origin_fails_closed(self):
        git(self.repo, "remote", "remove", "origin")
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_REMOTE_IDENTITY_NOT_VERIFIED"):
            self.verify()

    def test_invalid_sha_and_nonrepository_checkout_are_rejected(self):
        with self.assertRaisesRegex(RemoteRefHold, "INVALID_ARCHIVE_REMOTE_CONFIGURATION"):
            self.verify("0" * 39)
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_CHECKOUT_NOT_REPOSITORY_ROOT"):
            _verify_fixed_remote(self.repo / ".git", self.head, str(self.remote))

    def test_wrong_expected_sha_fails_before_remote_observation(self):
        with self.assertRaisesRegex(RemoteRefHold, "ARCHIVE_LOCAL_HEAD_MISMATCH"):
            self.verify(self.main)

    def test_unchanged_main_sha_and_no_remote_archive_write_by_gate(self):
        remote_before = git(self.repo, "ls-remote", "origin", ARCHIVE_REF).split()[0]
        main_before = git(self.repo, "ls-remote", "origin", "refs/heads/main").split()[0]
        self.verify()
        self.assertEqual(git(self.repo, "ls-remote", "origin", ARCHIVE_REF).split()[0],
                         remote_before)
        self.assertEqual(git(self.repo, "ls-remote", "origin", "refs/heads/main").split()[0],
                         main_before)


if __name__ == "__main__":
    unittest.main()
