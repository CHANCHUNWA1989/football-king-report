"""Real temporary Git tests: exact compressed evidence, no hosted writes."""
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ops.history_blob_retention_preflight import (
    REPO, SCHEMA, RetentionHold, inspect, main,
)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


class HistoryBlobRetentionPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="fk-retention-offline-")
        self.addCleanup(temp.cleanup)
        self.repo = Path(temp.name) / "repo"
        subprocess.run(["git", "init", str(self.repo)], check=True,
                       capture_output=True)
        (self.repo / "README").write_text("synthetic fixture only")
        self.base = self.commit("bootstrap")
        git(self.repo, "branch", "-M", "main")
        self.paths = ["history/2026/11/24/1-1.json.gz",
                      "forecast_provenance/2026/11/24/1-1/shadow.json.gz"]
        self.blobs = {}
        for i, path in enumerate(self.paths):
            self.blobs[path] = gzip.compress(f"synthetic {i}".encode(), mtime=0)
            self.write(path, self.blobs[path])
        self.source = self.commit("source gzip additions")
        self.manifest = self.build_manifest()

    def write(self, path, data):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def commit(self, message):
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=fixture", "-c",
            "user.email=fixture@example.org", "commit", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def build_manifest(self):
        rows = []
        for path, raw in sorted(self.blobs.items()):
            rows.append({"path": path, "compressed_bytes": len(raw),
                         "git_blob_sha1": git(self.repo, "rev-parse",
                                              self.source + ":" + path),
                         "sha256_compressed": hashlib.sha256(raw).hexdigest()})
        return {
            "schema": SCHEMA, "source_repo": REPO,
            "source_main_sha": self.source, "archive_bootstrap_sha": self.base,
            "source_added_gzip_paths": len(rows),
            "source_unique_git_blobs": len({r["git_blob_sha1"] for r in rows}),
            "compressed_bytes_sum": sum(r["compressed_bytes"] for r in rows),
            "digest_scope": "raw_compressed_git_blob_bytes_not_decompressed_JSON",
            "source_github_git_tree_truncated": False,
            "remote_archive_copy_confirmed": False,
            "independent_archive_retention_verified": False,
            "main_ruleset_activation_authorized": False,
            "production_recommendations": "DISABLED", "records": rows,
        }

    def test_exact_candidate_still_never_authorizes_release(self):
        r = inspect(self.repo, self.manifest, self.source)
        self.assertTrue(r["local_candidate_bytes_match"])
        self.assertEqual(r["source_manifest_verified_files"], 2)
        self.assertEqual(r["candidate_exact_match_files"], 2)
        self.assertFalse(r["remote_archive_copy_confirmed"])
        self.assertFalse(r["main_ruleset_activation_authorized"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_bootstrap_only_reports_every_missing_path(self):
        r = inspect(self.repo, self.manifest, self.base)
        self.assertEqual(r["candidate_exact_match_files"], 0)
        self.assertEqual(set(r["missing_paths"]), set(self.paths))
        self.assertFalse(r["local_candidate_bytes_match"])

    def test_divergent_candidate_one_missing_one_changed(self):
        git(self.repo, "checkout", "-b", "candidate", self.base)
        self.write(self.paths[0], gzip.compress(b"different", mtime=0))
        candidate = self.commit("synthetic changed evidence")
        r = inspect(self.repo, self.manifest, candidate)
        self.assertEqual(r["missing_paths"], [self.paths[1]])
        self.assertEqual(r["different_paths"], [self.paths[0]])
        self.assertFalse(r["local_candidate_bytes_match"])

    def test_omitted_record_with_corrected_totals_cannot_pass(self):
        self.manifest["records"].pop()
        row = self.manifest["records"][0]
        self.manifest.update(source_added_gzip_paths=1, source_unique_git_blobs=1,
                             compressed_bytes_sum=row["compressed_bytes"])
        with self.assertRaisesRegex(RetentionHold,
                                    "HISTORY_MANIFEST_INCOMPLETE_OR_EXTRA_PATH"):
            inspect(self.repo, self.manifest, self.source)

    def test_wrong_source_digest_rejected_even_for_correct_candidate(self):
        self.manifest["records"][0]["sha256_compressed"] = "0" * 64
        with self.assertRaisesRegex(RetentionHold,
                                    "SOURCE_HISTORY_MANIFEST_DIGEST_MISMATCH"):
            inspect(self.repo, self.manifest, self.source)

    def test_dirty_worktree_does_not_override_pinned_tree(self):
        self.write(self.paths[0], b"dirty working copy")
        before = git(self.repo, "status", "--porcelain")
        r = inspect(self.repo, self.manifest, self.source)
        self.assertTrue(r["local_candidate_bytes_match"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), before)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), self.source)

    def test_same_uncompressed_payload_different_gzip_bytes_is_different(self):
        self.write(self.paths[0], gzip.compress(b"synthetic 0", mtime=123))
        changed = self.commit("recompressed")
        r = inspect(self.repo, self.manifest, changed)
        self.assertEqual(r["different_paths"], [self.paths[0]])
        self.assertFalse(r["local_candidate_bytes_match"])

    def test_candidate_symlink_is_never_treated_as_regular_blob(self):
        p = self.repo / self.paths[0]
        p.unlink()
        p.symlink_to(self.repo / self.paths[1])
        changed = self.commit("unsafe link")
        with self.assertRaisesRegex(RetentionHold, "UNSAFE_HISTORY_TREE_ENTRY"):
            inspect(self.repo, self.manifest, changed)

    def test_invalid_manifest_paths_and_safety_flags_fail_closed(self):
        row = self.manifest["records"][0]
        original = row["path"]
        for path in ("../escape.gz", "/absolute.gz", "a/.git/private.gz"):
            row["path"] = path
            with self.subTest(path=path), self.assertRaises(RetentionHold):
                inspect(self.repo, self.manifest, self.source)
        row["path"] = original
        self.manifest["remote_archive_copy_confirmed"] = True
        with self.assertRaisesRegex(RetentionHold, "UNREVIEWED_HISTORY_MANIFEST"):
            inspect(self.repo, self.manifest, self.source)

    def test_cli_nonzero_on_exact_match_and_duplicate_keys(self):
        f = self.repo.parent / "manifest.json"
        f.write_text(json.dumps(self.manifest))
        args = ["--repo", str(self.repo), "--manifest", str(f),
                "--candidate-sha", self.source]
        for duplicate in (False, True):
            if duplicate:
                f.write_text(json.dumps(self.manifest)[:-1] +
                             ',"schema":"second"}')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rc = main(args)
            self.assertEqual(rc, 1)
            r = json.loads(output.getvalue())
            self.assertEqual(r["production_recommendations"], "DISABLED")
            if duplicate:
                self.assertEqual(r["status"], "HOLD_HISTORY_RETENTION_UNVERIFIABLE")
            else:
                self.assertTrue(r["local_candidate_bytes_match"])


if __name__ == "__main__":
    unittest.main()
