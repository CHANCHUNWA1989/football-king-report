"""Four-writer end-to-end archival CANARY: LOCAL bare Git only.

All input bytes are synthetic. This tests the full shared archive shape for
forecast provenance + settlement + NDR capture + OpenLiga capture without
GitHub credentials, a hosted write, branch protection or live provider data.
The real main/remote archive branches are NOT accessed or changed.
"""

import gzip
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from ops.archive_forecast_provenance import FILES
from ops.archive_remote_ref_gate import _verify_fixed_remote
from ops.isolated_capture_archive import append_capture
from ops.isolated_provenance_archive import (
    ARCHIVE_REF, ArchiveGateError, append as append_provenance,
)
from ops.isolated_settlement_archive import append as append_settlement
from ops.isolated_settlement_bridge import reconcile


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class FourWriterSharedArchiveCanaryTests(unittest.TestCase):
    DAY = "2026/11/23"

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fk-four-writer-local-only-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.remote = root / "archive.git"
        self.writer = root / "writer"
        self.reader = root / "reader"
        self.proof = root / "forecast"
        self.legacy = root / "legacy.json"
        self.incoming = root / "incoming.json"
        self.captures = {}
        self.proof.mkdir()

        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.writer)],
                       capture_output=True, check=True)
        (self.writer / "README.md").write_text(
            "synthetic fixture main; not football evidence\n")
        git(self.writer, "add", "README.md")
        git(self.writer, "-c", "user.name=offline-fixture",
            "-c", "user.email=offline@example.org",
            "commit", "-m", "Synthetic main baseline")
        git(self.writer, "branch", "-M", "main")
        git(self.writer, "push", "origin", "main")
        self.baseline = self.remote_head("refs/heads/main")

        for name in FILES:
            if name.endswith(".verification.json"):
                data = '[{"synthetic":true,"verified":false}]'
            elif name == "negative_checks.json":
                data = json.dumps({
                    "tampered_subject_rejected": True,
                    "wrong_source_digest_rejected": True,
                })
            elif name.endswith(".json"):
                data = '{"synthetic":true,"production_recommendations":"DISABLED"}'
            else:
                data = "synthetic fixture, not a signature or real odds"
            (self.proof / name).write_text(data)

        self.legacy.write_text(json.dumps(self.doc("legacy-fixture")))
        self.incoming.write_text(json.dumps(self.doc("new-fixture")))
        self.legacy_bytes = self.legacy.read_bytes()

        for kind in ("ndr", "openliga"):
            folder = root / (kind + "-capture-fixture")
            folder.mkdir()
            binary = io.BytesIO()
            with tarfile.open(fileobj=binary, mode="w") as stream:
                original = b"synthetic not independently signed: " + kind.encode()
                entry = tarfile.TarInfo("local-fixture.html")
                entry.size = len(original)
                stream.addfile(entry, io.BytesIO(original))
            (folder / (kind + "-capture.tar")).write_bytes(binary.getvalue())
            (folder / "capture.sigstore.json").write_bytes(
                b'{"synthetic_only":true,"signature_verified":false}\n')
            self.captures[kind] = folder

    @staticmethod
    def doc(key):
        return {
            "schema": "football-king-forward-research-1",
            "checked_utc": "2026-12-02T01:00:00+00:00",
            "samples": [{
                "key": key,
                "kickoff_utc": "2026-12-01T15:00:00+00:00",
                "forecast_utc": "2026-12-01T14:00:00+00:00",
                "market_utc": "2026-12-01T13:00:00+00:00",
                "y": 1, "p": [0.4, 0.3, 0.3], "m": [0.3, 0.4, 0.3],
                "fixture_result_source_independently_verified": False,
                "production_recommendations": "DISABLED",
            }],
            "n": 1,
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }

    def remote_head(self, ref):
        result = git(self.writer, "ls-remote", "origin", ref).split()
        self.assertEqual(result[1], ref)
        return result[0]

    def provision(self):
        # Provision ONLY a temporary local bare-Git branch, NEVER hosted GitHub.
        git(self.writer, "branch", "research/forward-provenance-archive",
            self.baseline)
        git(self.writer, "push", "origin", ARCHIVE_REF)
        self.assertEqual(self.remote_head(ARCHIVE_REF), self.baseline)

    def append(self, kind):
        if kind == "forecast":
            return append_provenance(
                self.proof, self.writer, "9001", "1", self.DAY, max_tries=1)
        if kind == "settlement":
            return append_settlement(
                self.incoming, self.legacy, self.writer,
                "9002", "1", self.DAY, max_tries=1)
        return append_capture(
            self.captures[kind], self.writer,
            {"ndr": "9003", "openliga": "9004"}[kind],
            "1", self.DAY, kind=kind, max_tries=1)

    def append_all(self, order=("forecast", "settlement", "ndr", "openliga")):
        return {kind: self.append(kind) for kind in order}

    def assert_main_unchanged(self, expected=None):
        self.assertEqual(self.remote_head("refs/heads/main"),
                         self.baseline if expected is None else expected)
        self.assertEqual(self.legacy.read_bytes(), self.legacy_bytes)

    def archived_content(self, sha, path):
        return subprocess.run(
            ["git", "-C", str(self.writer), "show", sha + ":" + path],
            check=True, capture_output=True,
        ).stdout

    def full_readback(self):
        sha = self.remote_head(ARCHIVE_REF)
        subprocess.run([
            "git", "clone", "--branch", "research/forward-provenance-archive",
            str(self.remote), str(self.reader),
        ], check=True, capture_output=True)
        self.assertEqual(git(self.reader, "rev-parse", "HEAD"), sha)
        pin = _verify_fixed_remote(self.reader, sha, str(self.remote))
        self.assertFalse(pin["remote_identity_independently_attested"])
        self.assertEqual(pin["production_recommendations"], "DISABLED")
        return sha

    def test_all_four_writers_commit_15_exact_gzip_blobs_to_one_archive(self):
        self.provision()
        receipts = self.append_all()
        self.assertEqual(
            {kind: info["new_files"] for kind, info in receipts.items()},
            {"forecast": 10, "settlement": 1, "ndr": 2, "openliga": 2})
        self.assertTrue(all(
            r["production_recommendations"] == "DISABLED"
            for r in receipts.values()))
        self.assertFalse(receipts["ndr"]["hosted_archive_write_authorized"])
        self.assertFalse(receipts["openliga"]["hosted_archive_write_authorized"])
        sha = self.full_readback()
        names = git(self.reader, "ls-tree", "-r", "--name-only", sha).splitlines()
        self.assertEqual(len([p for p in names if p.endswith(".gz")]), 15)
        for name in FILES:
            rel = f"forecast_provenance/{self.DAY}/9001-1/{name}.gz"
            self.assertIn(rel, names)
            self.assertEqual(gzip.decompress(self.archived_content(sha, rel)),
                             (self.proof / name).read_bytes())
        for kind, folder, run in (
            ("ndr", "ndr_capture_provenance", "9003"),
            ("openliga", "openliga_capture_provenance", "9004"),
        ):
            for name in (f"{kind}-capture.tar", "capture.sigstore.json"):
                rel = f"{folder}/{self.DAY}/{run}-1/{name}.gz"
                self.assertIn(rel, names)
                self.assertEqual(gzip.decompress(self.archived_content(sha, rel)),
                                 (self.captures[kind] / name).read_bytes())
        settlement_path = f"settlement_batches/{self.DAY}/9002-1.json.gz"
        self.assertIn(settlement_path, names)
        self.assertEqual(gzip.decompress(
            self.archived_content(sha, settlement_path)),
            self.incoming.read_bytes())
        merged, receipt = reconcile(self.legacy, self.reader, sha)
        self.assertEqual(receipt["archive_batches"], 1)
        self.assertEqual(receipt["legacy_samples"], 1)
        self.assertEqual(receipt["combined_samples"], 2)
        self.assertEqual({x["key"] for x in merged["samples"]},
                         {"legacy-fixture", "new-fixture"})
        self.assertFalse(receipt["remote_ref_checked"])
        self.assertFalse(receipt["profitability_verified"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assert_main_unchanged()

    def test_four_writers_in_interleaved_order_are_compatible(self):
        self.provision()
        self.append_all(("ndr", "forecast", "openliga", "settlement"))
        sha = self.remote_head(ARCHIVE_REF)
        names = git(self.writer, "ls-tree", "-r", "--name-only", sha).splitlines()
        self.assertEqual(len([p for p in names if p.endswith(".gz")]), 15)
        self.assert_main_unchanged()

    def test_all_four_replays_are_noop_with_identical_head(self):
        self.provision()
        self.append_all()
        prior = self.remote_head(ARCHIVE_REF)
        receipts = self.append_all(("openliga", "ndr", "settlement", "forecast"))
        self.assertEqual({r["status"] for r in receipts.values()},
                         {"ALREADY_ARCHIVED"})
        self.assertTrue(all(r["new_files"] == 0 for r in receipts.values()))
        self.assertEqual(self.remote_head(ARCHIVE_REF), prior)
        self.assert_main_unchanged()

    def test_all_four_collisions_reject_any_archive_rewrite(self):
        self.provision()
        self.append_all()
        original = self.remote_head(ARCHIVE_REF)
        for kind, path in (
            ("forecast", self.proof / "shadow.json"),
            ("settlement", self.incoming),
            ("ndr", self.captures["ndr"] / "capture.sigstore.json"),
            ("openliga", self.captures["openliga"] / "capture.sigstore.json"),
        ):
            before = path.read_bytes()
            try:
                path.write_bytes(before + b"\n")
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    self.append(kind)
            finally:
                path.write_bytes(before)
            self.assertEqual(self.remote_head(ARCHIVE_REF), original)
            self.assert_main_unchanged()

    def test_main_can_advance_independently_without_archive_contamination(self):
        self.provision()
        # Simulates an existing data publisher committing to main while the
        # immutable archive branch stays at the original preprovisioned SHA.
        marker = self.writer / "sources" / "six_league_free_latest.json"
        marker.parent.mkdir()
        marker.write_text('{"synthetic_status":"after-bootstrap"}\n')
        git(self.writer, "add", "sources")
        git(self.writer, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", "synthetic live-main status advancement")
        git(self.writer, "push", "origin", "HEAD:refs/heads/main")
        newer_main = self.remote_head("refs/heads/main")
        self.assertNotEqual(newer_main, self.baseline)
        self.assertEqual(self.remote_head(ARCHIVE_REF), self.baseline)

        receipts = self.append_all(("openliga", "forecast", "settlement", "ndr"))
        self.assertEqual(sum(r["new_files"] for r in receipts.values()), 15)
        pinned = self.remote_head(ARCHIVE_REF)
        self.assertNotEqual(pinned, newer_main)
        names = git(self.writer, "ls-tree", "-r", "--name-only", pinned)
        self.assertNotIn("six_league_free_latest.json", names)
        self.assertIn("sources/six_league_free_latest.json",
                      git(self.writer, "ls-tree", "-r", "--name-only", newer_main))
        self.assertEqual(git(self.writer, "merge-base", pinned, newer_main),
                         self.baseline)
        self.assert_main_unchanged(expected=newer_main)

    def test_missing_local_archive_ref_blocks_all_four_without_main_fallback(self):
        for kind in ("forecast", "settlement", "ndr", "openliga"):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                    ArchiveGateError, "ARCHIVE_BRANCH_NOT_PROVISIONED"):
                self.append(kind)
        self.assert_main_unchanged()


if __name__ == "__main__":
    unittest.main()
