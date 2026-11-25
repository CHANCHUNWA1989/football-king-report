"""True local Git integration tests, no network, provider, credentials or main writes."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.archive_forecast_provenance import FILES
from ops.isolated_provenance_archive import ArchiveGateError, append, ARCHIVE_REF


def git(where, *args):
    p = subprocess.run(["git", "-C", str(where), *args],
                       capture_output=True, text=True, check=True)
    return p.stdout.strip()


class IsolatedProvenanceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.clone = root / "clone"
        self.proof = root / "proof"
        self.proof.mkdir()
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.clone)],
                       capture_output=True, check=True)
        (self.clone / "README.md").write_text("main contents\n")
        git(self.clone, "add", "README.md")
        git(self.clone, "-c", "user.name=fixture", "-c", "user.email=fixture@example.com",
            "commit", "-m", "baseline")
        git(self.clone, "branch", "-M", "main")
        git(self.clone, "push", "origin", "main")
        self.main_sha = git(self.clone, "rev-parse", "main")
        for name in FILES:
            if name.endswith(".verification.json"):
                data = '[{"ok":true}]'
            elif name == "negative_checks.json":
                data = json.dumps({"tampered_subject_rejected": True,
                                   "wrong_source_digest_rejected": True})
            elif name.endswith(".json"):
                data = "{}"
            else:
                data = "rejected"
            (self.proof / name).write_text(data)

    def provision(self):
        git(self.clone, "branch", "research/forward-provenance-archive", "main")
        git(self.clone, "push", "origin", ARCHIVE_REF)

    def test_existing_fixed_branch_append_and_idempotent_replay(self):
        self.provision()
        first = append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        self.assertEqual(first["status"], "ARCHIVED_ON_ISOLATED_BRANCH")
        self.assertEqual(first["new_files"], 10)
        self.assertEqual(git(self.clone, "ls-remote", "origin", "refs/heads/main").split()[0],
                         self.main_sha)
        archived = git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0]
        paths = git(self.clone, "ls-tree", "-r", "--name-only", archived).splitlines()
        self.assertEqual(len([p for p in paths if p.startswith("forecast_provenance/")]), 10)
        replay = append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        self.assertEqual(replay["status"], "ALREADY_ARCHIVED")
        self.assertEqual(git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0], archived)

    def test_missing_remote_archive_branch_fails_closed(self):
        with self.assertRaisesRegex(ArchiveGateError, "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        self.assertEqual(git(self.clone, "ls-remote", "origin", "refs/heads/main").split()[0],
                         self.main_sha)

    def test_changed_proof_cannot_rewrite_existing_archive(self):
        self.provision()
        append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        old = git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0]
        (self.proof / "shadow.json").write_text('{"tampered":true}')
        with self.assertRaisesRegex(ValueError, "IMMUTABLE_PROVENANCE_ARCHIVE_COLLISION"):
            append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        self.assertEqual(git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0], old)
        self.assertEqual(git(self.clone, "ls-remote", "origin", "refs/heads/main").split()[0],
                         self.main_sha)

    def test_bad_untrusted_source_never_changes_archive(self):
        self.provision()
        old = git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0]
        (self.proof / "shadow.json").unlink()
        with self.assertRaises(ValueError):
            append(self.proof, self.clone, "777", "1", "2026/11/23", max_tries=1)
        self.assertEqual(git(self.clone, "ls-remote", "origin", ARCHIVE_REF).split()[0], old)

    def test_main_branch_is_unmodified_on_second_run(self):
        self.provision()
        for run_id in ("777", "778"):
            append(self.proof, self.clone, run_id, "1", "2026/11/23", max_tries=1)
        self.assertEqual(git(self.clone, "ls-remote", "origin", "refs/heads/main").split()[0],
                         self.main_sha)


if __name__ == "__main__":
    unittest.main()
