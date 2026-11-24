"""Temporary bare-Git tests for shadow NDR/OpenLiga archive migration pilot."""

import gzip
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from ops.archive_local_fixture_guard import LocalFixtureOnlyHold
from ops.archive_remote_ref_gate import OFFICIAL_ORIGIN
from ops.isolated_capture_archive import append_capture
from ops.isolated_provenance_archive import ARCHIVE_REF, ArchiveGateError


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True).stdout.strip()


class IsolatedCaptureArchiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="fk-ndr-openliga-local-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.bare = root / "archive.git"
        self.repo = root / "checkout"
        self.proofs = {}
        subprocess.run(["git", "init", "--bare", str(self.bare)],
                       check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.bare), str(self.repo)],
                       check=True, capture_output=True)
        (self.repo / "README.md").write_text("local synthetic main sentinel\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", "initial local main")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "origin", "main")
        self.main = self.head("refs/heads/main")
        for kind in ("ndr", "openliga"):
            proof = root / (kind + "-proof")
            proof.mkdir()
            binary = io.BytesIO()
            with tarfile.open(fileobj=binary, mode="w") as stream:
                payload = (kind + " synthetic fixture").encode()
                info = tarfile.TarInfo("fixture.html")
                info.size = len(payload)
                stream.addfile(info, io.BytesIO(payload))
            (proof / (kind + "-capture.tar")).write_bytes(binary.getvalue())
            (proof / "capture.sigstore.json").write_bytes(
                b'{"synthetic_only":true,"signed":false}\n')
            self.proofs[kind] = proof

    def head(self, ref):
        return git(self.repo, "ls-remote", str(self.bare), ref).split()[0]

    def provision(self):
        git(self.repo, "branch", "research/forward-provenance-archive", "main")
        git(self.repo, "push", "origin", ARCHIVE_REF)

    def append(self, kind="ndr", run="777", attempt="1"):
        return append_capture(self.proofs[kind], self.repo, run, attempt,
                              "2026/11/23", kind=kind)

    def assert_main_untouched(self):
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_both_capture_families_share_one_local_branch_no_main_write(self):
        self.provision()
        first = self.append("ndr")
        second = self.append("openliga", run="778")
        self.assertEqual(first["status"], "CAPTURE_ARCHIVED_LOCAL_FIXTURE_ONLY")
        self.assertEqual(second["status"], "CAPTURE_ARCHIVED_LOCAL_FIXTURE_ONLY")
        self.assertEqual(first["new_files"], 2)
        self.assertEqual(second["new_files"], 2)
        self.assertFalse(first["hosted_archive_write_authorized"])
        self.assertFalse(second["hosted_archive_write_authorized"])
        self.assertEqual(second["production_recommendations"], "DISABLED")
        sha = self.head(ARCHIVE_REF)
        files = git(self.repo, "ls-tree", "-r", "--name-only", sha).splitlines()
        for kind, folder, run in (
            ("ndr", "ndr_capture_provenance", "777"),
            ("openliga", "openliga_capture_provenance", "778"),
        ):
            for original in (kind + "-capture.tar", "capture.sigstore.json"):
                path = f"{folder}/2026/11/23/{run}-1/{original}.gz"
                self.assertIn(path, files)
                compressed = subprocess.run(
                    ["git", "-C", str(self.repo), "show", f"{sha}:{path}"],
                    check=True, capture_output=True).stdout
                self.assertEqual(gzip.decompress(compressed),
                                 (self.proofs[kind] / original).read_bytes())
        self.assert_main_untouched()

    def test_replay_of_both_batches_is_deterministic(self):
        self.provision()
        self.append("ndr")
        self.append("openliga", run="778")
        before = self.head(ARCHIVE_REF)
        for kind, run in (("ndr", "777"), ("openliga", "778")):
            receipt = self.append(kind, run=run)
            self.assertEqual(receipt["status"], "ALREADY_ARCHIVED")
            self.assertEqual(receipt["new_files"], 0)
            self.assertFalse(receipt["hosted_archive_write_authorized"])
        self.assertEqual(self.head(ARCHIVE_REF), before)
        self.assert_main_untouched()

    def test_same_run_payload_collision_cannot_change_archive(self):
        self.provision()
        self.append("ndr")
        self.append("openliga", run="778")
        before = self.head(ARCHIVE_REF)
        for kind, run in (("ndr", "777"), ("openliga", "778")):
            path = self.proofs[kind] / "capture.sigstore.json"
            saved = path.read_bytes()
            path.write_bytes(b'{"changed":true}')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.append(kind, run=run)
            path.write_bytes(saved)
            self.assertEqual(self.head(ARCHIVE_REF), before)
        self.assert_main_untouched()

    def test_missing_archive_branch_fails_without_fallback(self):
        with self.assertRaisesRegex(ArchiveGateError,
                                    "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            self.append("ndr")
        with self.assertRaisesRegex(ArchiveGateError,
                                    "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            self.append("openliga")
        self.assert_main_untouched()

    def test_unknown_capture_kind_refused_before_remote_call(self):
        with patch("ops.isolated_capture_archive._remote_head") as remote:
            with self.assertRaisesRegex(ArchiveGateError, "INVALID_CAPTURE_FAMILY"):
                append_capture(self.proofs["ndr"], self.repo, "777", "1",
                               "2026/11/23", kind="unrecognized")
            remote.assert_not_called()
        self.assert_main_untouched()

    def test_hosted_remote_is_rejected_before_remote_query(self):
        git(self.repo, "remote", "set-url", "origin", OFFICIAL_ORIGIN)
        with patch("ops.isolated_capture_archive._remote_head") as remote:
            for kind in ("ndr", "openliga"):
                with self.subTest(kind=kind), self.assertRaisesRegex(
                        LocalFixtureOnlyHold, "LOCAL_FIXTURE_REMOTE_NOT_LOCAL_PATH"):
                    self.append(kind)
            remote.assert_not_called()
        self.assert_main_untouched()


if __name__ == "__main__":
    unittest.main()
