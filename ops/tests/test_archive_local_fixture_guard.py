"""Real local Git fixtures prove generic archive writers cannot target GitHub."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ops.archive_local_fixture_guard import (
    LocalFixtureOnlyHold, require_local_fixture_git_origin,
)
from ops.archive_remote_ref_gate import OFFICIAL_ORIGIN
from ops import isolated_provenance_archive as provenance
from ops import isolated_settlement_archive as settlement


def git(where, *args):
    return subprocess.run(
        ["git", "-C", str(where), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class LocalArchiveFixtureOnlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fk-local-fixture-only-")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.bare = base / "fixture.git"
        self.clone = base / "checkout"
        self.other = base / "other.git"
        subprocess.run(["git", "init", "--bare", str(self.bare)],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", str(self.bare), str(self.clone)],
                       capture_output=True, check=True)
        (self.clone / "README.md").write_text("synthetic only\n")
        git(self.clone, "add", "README.md")
        git(self.clone, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", "synthetic main")
        git(self.clone, "branch", "-M", "main")
        git(self.clone, "push", "origin", "main")
        self.main_sha = git(self.clone, "rev-parse", "HEAD")

    def main_remote(self):
        return git(self.clone, "ls-remote", str(self.bare),
                   "refs/heads/main").split()[0]

    def test_real_bare_git_fixture_is_allowed_without_hosted_authority(self):
        receipt = require_local_fixture_git_origin(self.clone)
        self.assertEqual(receipt["status"], "LOCAL_BARE_GIT_FIXTURE_ONLY")
        self.assertFalse(receipt["hosted_archive_write_authorized"])
        self.assertFalse(receipt["main_ruleset_activation_authorized"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_generic_both_writers_reject_hosted_origin_before_any_remote_call(self):
        # No real network request is allowed in this test.
        git(self.clone, "remote", "set-url", "origin", OFFICIAL_ORIGIN)
        with mock.patch.object(provenance, "_remote_head") as probe:
            with self.assertRaisesRegex(
                    LocalFixtureOnlyHold,
                    "LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH"):
                provenance.append(
                    self.clone / "nonexistent-proof", self.clone,
                    "1", "1", "2026/11/23", max_tries=1)
            probe.assert_not_called()
        with mock.patch.object(settlement, "_remote_head") as probe:
            with self.assertRaisesRegex(
                    LocalFixtureOnlyHold,
                    "LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH"):
                settlement.append(
                    self.clone / "nonexistent-new",
                    self.clone / "nonexistent-legacy", self.clone,
                    "1", "1", "2026/11/23", max_tries=1)
            probe.assert_not_called()
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_http_ssh_scp_file_scheme_and_relative_origin_rejected(self):
        destinations = [
            OFFICIAL_ORIGIN,
            "https://example.org/other.git",
            "ssh://git@github.com/org/repo",
            "git@github.com:org/repo",
            "file:///tmp/example.git",
            "../relative.git",
        ]
        for address in destinations:
            with self.subTest(address=address):
                git(self.clone, "remote", "set-url", "origin", address)
                with self.assertRaisesRegex(
                        LocalFixtureOnlyHold,
                        "LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH"):
                    require_local_fixture_git_origin(self.clone)
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_pushurl_mirror_and_remote_push_refspec_rejected(self):
        for key, value in (
            ("remote.origin.pushurl", OFFICIAL_ORIGIN),
            ("remote.origin.mirror", "true"),
            ("remote.origin.push", "HEAD:refs/heads/main"),
            ("remote.origin.receivepack", "fake-handler"),
        ):
            with self.subTest(key=key):
                git(self.clone, "config", "--local", key, value)
                with self.assertRaisesRegex(
                        LocalFixtureOnlyHold,
                        "LOCAL_FIXTURE_GIT_REDIRECTION_UNTRUSTED"):
                    require_local_fixture_git_origin(self.clone)
                git(self.clone, "config", "--local", "--unset", key)

    def test_git_rewrites_includes_hooks_and_credentials_rejected(self):
        for key, value in (
            ("url.https://github.com/.insteadOf", str(self.bare)),
            ("include.path", "/tmp/unreviewed-config"),
            ("includeIf.gitdir:/tmp/.path", "/tmp/unreviewed-config"),
            ("core.hooksPath", "/tmp/unreviewed-hooks"),
            ("credential.helper", "store"),
        ):
            with self.subTest(key=key):
                git(self.clone, "config", "--local", key, value)
                with self.assertRaisesRegex(
                        LocalFixtureOnlyHold,
                        "LOCAL_FIXTURE_GIT_REDIRECTION_UNTRUSTED"):
                    require_local_fixture_git_origin(self.clone)
                git(self.clone, "config", "--local", "--unset", key)

    def test_duplicate_origin_urls_are_rejected_even_if_last_is_local(self):
        git(self.clone, "config", "--local", "--add",
            "remote.origin.url", OFFICIAL_ORIGIN)
        git(self.clone, "config", "--local", "--add",
            "remote.origin.url", str(self.bare))
        with self.assertRaisesRegex(
                LocalFixtureOnlyHold, "LOCAL_FIXTURE_ORIGIN_NOT_UNIQUE"):
            require_local_fixture_git_origin(self.clone)
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_symlink_alias_to_local_bare_repo_is_rejected(self):
        alias = self.bare.parent / "alias.git"
        alias.symlink_to(self.bare, target_is_directory=True)
        git(self.clone, "remote", "set-url", "origin", str(alias))
        with self.assertRaisesRegex(
                LocalFixtureOnlyHold, "LOCAL_FIXTURE_REMOTE_PATH_UNTRUSTED"):
            require_local_fixture_git_origin(self.clone)
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_nonbare_destination_is_rejected(self):
        git(self.clone, "remote", "set-url", "origin", str(self.clone))
        with self.assertRaisesRegex(
                LocalFixtureOnlyHold, "LOCAL_FIXTURE_REMOTE_NOT_BARE_REPOSITORY"):
            require_local_fixture_git_origin(self.clone)
        self.assertEqual(self.main_remote(), self.main_sha)

    def test_nonrepository_and_missing_origin_fail_closed(self):
        with self.assertRaises(LocalFixtureOnlyHold):
            require_local_fixture_git_origin(self.clone / "README.md")
        git(self.clone, "remote", "remove", "origin")
        with self.assertRaisesRegex(
                LocalFixtureOnlyHold, "LOCAL_FIXTURE_CONFIG_UNVERIFIABLE"):
            require_local_fixture_git_origin(self.clone)
        self.assertEqual(self.main_remote(), self.main_sha)


if __name__ == "__main__":
    unittest.main()
