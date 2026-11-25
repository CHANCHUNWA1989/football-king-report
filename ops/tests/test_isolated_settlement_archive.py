"""Real local bare-Git tests for research settlement writer, no GitHub writes."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.isolated_provenance_archive import ARCHIVE_REF, ArchiveGateError
from ops.isolated_settlement_archive import append
from ops.isolated_settlement_bridge import reconcile


def git(where, *args):
    return subprocess.run(["git", "-C", str(where), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


class IsolatedSettlementArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.remote = root / "remote.git"
        self.clone = root / "clone"
        self.old = root / "legacy.json"
        self.incoming = root / "incoming.json"
        self.checkout = root / "read-checkout"
        subprocess.run(["git", "init", "--bare", str(self.remote)],
                       check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.clone)],
                       check=True, capture_output=True)
        (self.clone / "README.md").write_text("this is main\n")
        git(self.clone, "add", "README.md")
        git(self.clone, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.com", "commit", "-m", "main")
        git(self.clone, "branch", "-M", "main")
        git(self.clone, "push", "origin", "main")
        self.main = git(self.clone, "rev-parse", "main")
        self.kickoff = datetime(2026, 12, 1, 15, tzinfo=timezone.utc)
        self.original = self.doc([self.sample("legacy")])
        self.new = self.doc([self.sample("new")])
        self.old.write_text(json.dumps(self.original))
        self.old_bytes = self.old.read_bytes()
        self.incoming.write_text(json.dumps(self.new))

    def sample(self, key):
        return {
            "key": key,
            "kickoff_utc": self.kickoff.isoformat(),
            "forecast_utc": (self.kickoff - timedelta(hours=1)).isoformat(),
            "market_utc": (self.kickoff - timedelta(hours=2)).isoformat(),
            "y": 1,
            "p": [0.4, 0.3, 0.3], "m": [0.3, 0.4, 0.3],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }

    @staticmethod
    def doc(samples):
        return {
            "schema": "football-king-forward-research-1",
            "checked_utc": "2026-12-02T01:00:00+00:00",
            "samples": samples, "n": len(samples),
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }

    def provision(self):
        git(self.clone, "branch", "research/forward-provenance-archive", "main")
        git(self.clone, "push", "origin", ARCHIVE_REF)

    def head(self, ref=ARCHIVE_REF):
        return git(self.clone, "ls-remote", "origin", ref).split()[0]

    def write(self, run="123", attempt="1", day="2026/11/23"):
        return append(self.incoming, self.old, self.clone,
                      run, attempt, day, max_tries=1)

    def readback(self):
        sha = self.head()
        subprocess.run(["git", "clone", "--branch",
                        "research/forward-provenance-archive",
                        str(self.remote), str(self.checkout)],
                       check=True, capture_output=True)
        self.assertEqual(git(self.checkout, "rev-parse", "HEAD"), sha)
        return reconcile(self.old, self.checkout, sha)

    def test_append_replay_and_read_compatible_without_main_write(self):
        self.provision()
        result = self.write()
        self.assertEqual(result["status"], "SETTLEMENT_ARCHIVED_RESEARCH_ONLY")
        self.assertEqual(result["new_files"], 1)
        archived = self.head()
        replay = self.write()
        self.assertEqual(replay["status"], "ALREADY_ARCHIVED")
        self.assertEqual(self.head(), archived)
        merged, receipt = self.readback()
        self.assertEqual((merged["n"], receipt["new_samples"]), (2, 1))
        self.assertEqual(merged["production_recommendations"], "DISABLED")
        self.assertEqual(self.old.read_bytes(), self.old_bytes)
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_second_batch_preserves_two_distinct_new_records(self):
        self.provision()
        self.write()
        self.incoming.write_text(json.dumps(self.doc([self.sample("third")])))
        self.write(run="124")
        combined, receipt = self.readback()
        self.assertEqual((combined["n"], receipt["archive_batches"],
                          receipt["new_samples"]), (3, 2, 2))
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_unprovisioned_archive_ref_fails_closed(self):
        with self.assertRaisesRegex(ArchiveGateError, "ARCHIVE_BRANCH_NOT_PROVISIONED"):
            self.write()
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_different_result_for_old_fixture_rejected_before_remote(self):
        altered = self.sample("legacy")
        altered["y"] = 2
        self.incoming.write_text(json.dumps(self.doc([altered])))
        with self.assertRaisesRegex(ValueError, "CONFLICTING_RESULT"):
            self.write()
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_cross_batch_changed_result_fails_without_rewrite(self):
        self.provision()
        self.write()
        before = self.head()
        altered = self.sample("new")
        altered["y"] = 0
        self.incoming.write_text(json.dumps(self.doc([altered])))
        with self.assertRaisesRegex(ValueError, "CONFLICTING_RESULT"):
            self.write(run="124")
        self.assertEqual(self.head(), before)
        self.assertEqual(self.head("refs/heads/main"), self.main)

    def test_same_batch_different_raw_bytes_rejected(self):
        self.provision()
        self.write()
        before = self.head()
        self.incoming.write_text(json.dumps(self.new, indent=2) + "\n")
        with self.assertRaisesRegex(
                ArchiveGateError, "IMMUTABLE_SETTLEMENT_BATCH_COLLISION"):
            self.write()
        self.assertEqual(self.head(), before)

    def test_unsafe_enabled_source_rejected(self):
        self.provision()
        old = self.head()
        enabled = dict(self.new)
        enabled["production_recommendations"] = "ENABLED"
        self.incoming.write_text(json.dumps(enabled))
        with self.assertRaisesRegex(ValueError, "INVALID_EVIDENCE_SAFETY"):
            self.write()
        self.assertEqual(self.head(), old)

    def test_invalid_date_and_identifiers_fail_closed(self):
        self.provision()
        old = self.head()
        for run, day in (("../10", "2026/11/23"),
                         ("123", "2026/02/30"),
                         ("000", "2026/11/23")):
            with self.subTest(run=run, day=day):
                with self.assertRaisesRegex(
                        ArchiveGateError, "INVALID_SETTLEMENT"):
                    self.write(run=run, day=day)
        self.assertEqual(self.head(), old)

    def test_missing_legacy_is_not_treated_as_empty(self):
        self.provision()
        old = self.head()
        self.old.unlink()
        with self.assertRaisesRegex(ValueError, "UNSAFE_OR_MISSING_SETTLEMENT_FILE"):
            self.write()
        self.assertEqual(self.head(), old)

    def test_duplicate_key_and_nonfinite_source_rejected(self):
        self.provision()
        old = self.head()
        for raw in ('{"schema":"x","schema":"x"}',
                    '{"schema":"x","n":NaN}'):
            with self.subTest(raw=raw):
                self.incoming.write_text(raw)
                with self.assertRaises(ValueError):
                    self.write()
                self.assertEqual(self.head(), old)

    def test_existing_provenance_folder_untouched(self):
        self.provision()
        git(self.clone, "fetch", "origin", ARCHIVE_REF)
        git(self.clone, "checkout", "-B", "research/forward-provenance-archive",
            "FETCH_HEAD")
        proof = self.clone / "forecast_provenance" / "2026" / "11" / "23"
        proof.mkdir(parents=True)
        (proof / "example.txt").write_text("pre-existing proof")
        git(self.clone, "add", "forecast_provenance")
        git(self.clone, "-c", "user.name=fixture",
            "-c", "user.email=fixture@example.com", "commit", "-m", "prior proof")
        git(self.clone, "push", "origin", ARCHIVE_REF)
        self.write()
        sha = self.head()
        lines = git(self.clone, "ls-tree", "-r", "--name-only", sha)
        self.assertIn("forecast_provenance/2026/11/23/example.txt", lines)
        self.assertIn("settlement_batches/2026/11/23/123-1.json.gz", lines)
        self.assertEqual(self.head("refs/heads/main"), self.main)


if __name__ == "__main__":
    unittest.main()
