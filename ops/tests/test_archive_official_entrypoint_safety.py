"""Both official archive CLI entrypoints must reject unapproved Git remotes.

This suite creates ONLY temporary local bare Git repositories. It never touches
the real GitHub archive, main branch, credentials or public research artifacts.
"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ops.archive_forecast_provenance import FILES
from ops.archive_remote_ref_gate import RemoteRefHold
from ops.isolated_provenance_archive import ARCHIVE_REF


def git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


class ArchiveOfficialEntrypointSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.temp = tempfile.TemporaryDirectory(prefix="fk-official-cli-offline-")
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.remote = folder / "local-only.git"
        self.repo = folder / "clone"
        self.proof = folder / "proof"
        self.proof.mkdir()
        self.legacy = folder / "legacy.json"
        self.source = folder / "source.json"
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       capture_output=True, check=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.repo)],
                       capture_output=True, check=True)
        (self.repo / "README.md").write_text("offline sentinel\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "-c", "user.name=offline",
            "-c", "user.email=fixture@example.org",
            "commit", "-m", "synthetic main")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "origin", "main")
        git(self.repo, "branch", "research/forward-provenance-archive", "main")
        git(self.repo, "push", "origin", ARCHIVE_REF)
        self.initial_main = self.remote_sha("refs/heads/main")
        self.initial_archive = self.remote_sha(ARCHIVE_REF)
        for filename in FILES:
            if filename.endswith(".verification.json"):
                value = '[{"ok":true}]'
            elif filename == "negative_checks.json":
                value = json.dumps({"tampered_subject_rejected": True,
                                    "wrong_source_digest_rejected": True})
            elif filename.endswith(".json"):
                value = "{}"
            else:
                value = "synthetic audit text"
            (self.proof / filename).write_text(value)
        def doc(key):
            return {
                "schema": "football-king-forward-research-1",
                "checked_utc": "2026-12-02T01:00:00+00:00",
                "samples": [{
                    "key": key,
                    "kickoff_utc": "2026-12-01T15:00:00+00:00",
                    "forecast_utc": "2026-12-01T14:00:00+00:00",
                    "market_utc": "2026-12-01T13:00:00+00:00",
                    "y": 1,
                    "p": [0.4, 0.3, 0.3],
                    "m": [0.3, 0.4, 0.3],
                    "fixture_result_source_independently_verified": False,
                    "production_recommendations": "DISABLED",
                }],
                "n": 1,
                "results_independently_verified": False,
                "profitability_verified": False,
                "production_recommendations": "DISABLED",
            }
        self.legacy.write_text(json.dumps(doc("synthetic-old")))
        self.source.write_text(json.dumps(doc("synthetic-new")))
        self.legacy_raw = self.legacy.read_bytes()

    def remote_sha(self, ref):
        return git(self.repo, "ls-remote", "origin", ref).split()[0]

    def assert_remote_unchanged(self):
        self.assertEqual(self.remote_sha("refs/heads/main"), self.initial_main)
        self.assertEqual(self.remote_sha(ARCHIVE_REF), self.initial_archive)
        self.assertEqual(self.legacy.read_bytes(), self.legacy_raw)

    def cli(self, module):
        args = [sys.executable, "-m", module,
                "--repo", str(self.repo),
                "--run-id", "9001",
                "--attempt", "1",
                "--day", "2026/11/23"]
        if module.endswith("isolated_provenance_archive"):
            args += ["--proof", str(self.proof)]
        else:
            args += ["--source", str(self.source), "--legacy", str(self.legacy)]
        return subprocess.run(args, cwd=self.root,
                              capture_output=True, text=True, check=False)

    def test_real_provenance_cli_rejects_local_git_origin_without_writes(self):
        proc = self.cli("ops.isolated_provenance_archive")
        self.assertEqual(proc.returncode, 1, proc.stderr[:200])
        receipt = json.loads(proc.stdout)
        self.assertEqual(receipt["status"], "HOLD_ARCHIVE_NOT_CONFIRMED")
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assert_remote_unchanged()

    def test_real_settlement_cli_rejects_local_git_origin_without_writes(self):
        proc = self.cli("ops.isolated_settlement_archive")
        self.assertEqual(proc.returncode, 1, proc.stderr[:200])
        receipt = json.loads(proc.stdout)
        self.assertEqual(receipt["status"],
                         "HOLD_SETTLEMENT_ARCHIVE_NOT_CONFIRMED")
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assert_remote_unchanged()

    def test_provenance_official_wrapper_checks_before_and_after_append(self):
        from ops import isolated_provenance_archive as module
        with patch.object(module, "verify_archive_writer_origin") as gate, patch.object(
                module, "append", return_value={
                    "status": "ARCHIVED_ON_ISOLATED_BRANCH",
                    "production_recommendations": "DISABLED",
                }) as write:
            result = module.append_official(
                self.proof, self.repo, "9001", "1", "2026/11/23")
        self.assertEqual(gate.call_count, 2)
        write.assert_called_once()
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assert_remote_unchanged()

    def test_settlement_official_wrapper_checks_before_and_after_append(self):
        from ops import isolated_settlement_archive as module
        with patch.object(module, "verify_archive_writer_origin") as gate, patch.object(
                module, "append", return_value={
                    "status": "SETTLEMENT_ARCHIVED_RESEARCH_ONLY",
                    "production_recommendations": "DISABLED",
                }) as write:
            result = module.append_official(
                self.source, self.legacy, self.repo, "9002", "1", "2026/11/23")
        self.assertEqual(gate.call_count, 2)
        write.assert_called_once()
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assert_remote_unchanged()

    def test_provenance_invalid_origin_does_not_call_writer(self):
        from ops import isolated_provenance_archive as module
        with patch.object(module, "verify_archive_writer_origin",
                          side_effect=RemoteRefHold(
                              "ARCHIVE_WRITER_ORIGIN_MISMATCH")) as gate, patch.object(
                                  module, "append") as write:
            with self.assertRaisesRegex(RemoteRefHold,
                                        "ARCHIVE_WRITER_ORIGIN_MISMATCH"):
                module.append_official(
                    self.proof, self.repo, "9001", "1", "2026/11/23")
        gate.assert_called_once_with(self.repo)
        write.assert_not_called()
        self.assert_remote_unchanged()

    def test_settlement_invalid_origin_does_not_call_writer(self):
        from ops import isolated_settlement_archive as module
        with patch.object(module, "verify_archive_writer_origin",
                          side_effect=RemoteRefHold(
                              "ARCHIVE_WRITER_ORIGIN_MISMATCH")) as gate, patch.object(
                                  module, "append") as write:
            with self.assertRaisesRegex(RemoteRefHold,
                                        "ARCHIVE_WRITER_ORIGIN_MISMATCH"):
                module.append_official(
                    self.source, self.legacy, self.repo, "9002", "1", "2026/11/23")
        gate.assert_called_once_with(self.repo)
        write.assert_not_called()
        self.assert_remote_unchanged()

    def test_postwrite_identity_failure_is_never_accepted_as_success(self):
        from ops import isolated_settlement_archive as settlement
        from ops import isolated_provenance_archive as provenance
        for module, argv in (
            (provenance, (self.proof, self.repo, "9001", "1", "2026/11/23")),
            (settlement, (self.source, self.legacy, self.repo,
                          "9002", "1", "2026/11/23")),
        ):
            with self.subTest(module=module.__name__), patch.object(
                module, "verify_archive_writer_origin",
                side_effect=[None, RemoteRefHold("ARCHIVE_WRITER_ORIGIN_MISMATCH")]
            ) as gate, patch.object(
                module, "append", return_value={"production_recommendations": "DISABLED"}
            ) as write:
                with self.assertRaisesRegex(
                        RemoteRefHold, "ARCHIVE_WRITER_ORIGIN_MISMATCH"):
                    module.append_official(*argv)
                self.assertEqual(gate.call_count, 2)
                write.assert_called_once()
            self.assert_remote_unchanged()


if __name__ == "__main__":
    unittest.main()
