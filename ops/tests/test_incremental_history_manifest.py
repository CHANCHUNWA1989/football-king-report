"""Local real-Git tests and actual pinned 35->52 manifest lineage contract."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops.history_blob_retention_preflight import REPO, SCHEMA, RetentionHold
from ops.incremental_history_manifest import inspect, lineage, _git_blob_id


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def encode(doc):
    return (json.dumps(doc, sort_keys=True) + "\n").encode()


class IncrementalHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = Path(tmp.name)
        git(self.repo, "init")
        (self.repo / "README").write_text("synthetic only")
        self.base = self.commit("base")
        self.a = "history/a.json.gz"
        self.b = "history/b.json.gz"
        self.c = "history/c.json.gz"
        self.raw_a = gzip.compress(b"old synthetic", mtime=0)
        self.raw_c = gzip.compress(b"new synthetic", mtime=0)
        self.write(self.a, self.raw_a)
        self.before = self.commit("first history")
        self.old = self.manifest(self.before, {self.a: self.raw_a})
        self.old_raw = encode(self.old)
        self.write(self.b, self.raw_a)
        self.write(self.c, self.raw_c)
        self.after = self.commit("add duplicated and novel content")
        self.new = self.manifest(self.after, {self.a: self.raw_a,
                                            self.b: self.raw_a, self.c: self.raw_c})
        self.new.update(previous_source_main_sha=self.before,
                        previous_manifest_git_blob_sha1=_git_blob_id(self.old_raw),
                        previous_manifest_path_count=1,
                        incremental_added_paths=2,
                        incremental_rehashed_unique_blobs=1)

    def write(self, path, raw):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)

    def commit(self, message):
        git(self.repo, "add", "-A")
        git(self.repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.org",
            "commit", "-m", message)
        return git(self.repo, "rev-parse", "HEAD")

    def manifest(self, sha, data):
        records = [
            {"path": p, "compressed_bytes": len(raw),
             "git_blob_sha1": _git_blob_id(raw),
             "sha256_compressed": hashlib.sha256(raw).hexdigest()}
            for p, raw in sorted(data.items())
        ]
        return {"schema": SCHEMA, "source_repo": REPO,
                "source_main_sha": sha, "archive_bootstrap_sha": self.base,
                "source_added_gzip_paths": len(records),
                "source_unique_git_blobs": len({x["git_blob_sha1"] for x in records}),
                "compressed_bytes_sum": sum(x["compressed_bytes"] for x in records),
                "digest_scope": "raw_compressed_git_blob_bytes_not_decompressed_JSON",
                "source_github_git_tree_truncated": False,
                "remote_archive_copy_confirmed": False,
                "independent_archive_retention_verified": False,
                "main_ruleset_activation_authorized": False,
                "production_recommendations": "DISABLED", "records": records}

    def test_only_novel_blob_readback_and_no_release(self):
        from ops.incremental_history_manifest import _blob
        with patch("ops.incremental_history_manifest._blob", wraps=_blob) as read:
            r = inspect(self.repo, self.old_raw, encode(self.new))
        self.assertEqual(read.call_count, 1)
        self.assertEqual(r["new_paths"], 2)
        self.assertEqual(r["new_unique_blobs_hashed"], 1)
        self.assertFalse(r["inherited_sha256_rehashed"])
        self.assertFalse(r["independent_archive_retention_verified"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_previous_digest_change_rejected(self):
        self.new["records"][0]["sha256_compressed"] = "a" * 64
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_PREVIOUS_HISTORY_CHANGED"):
            lineage(self.old_raw, encode(self.new))

    def test_duplicate_blob_conflicting_digest_rejected(self):
        self.new["records"][1]["sha256_compressed"] = "a" * 64
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_CONFLICTING_BLOB_DIGEST"):
            lineage(self.old_raw, encode(self.new))

    def test_new_raw_digest_mismatch_rejected(self):
        self.new["records"][2]["sha256_compressed"] = "a" * 64
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_NEW_RAW_DIGEST_MISMATCH"):
            inspect(self.repo, self.old_raw, encode(self.new))

    def test_omitted_new_path_even_with_corrected_totals_rejected(self):
        row = self.new["records"].pop(1)
        self.new["source_added_gzip_paths"] -= 1
        self.new["compressed_bytes_sum"] -= row["compressed_bytes"]
        self.new["incremental_added_paths"] -= 1
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_INCOMPLETE_ADDITION_SET"):
            inspect(self.repo, self.old_raw, encode(self.new))

    def test_changed_old_git_history_rejected(self):
        self.write(self.a, gzip.compress(b"altered", mtime=0))
        self.new["source_main_sha"] = self.commit("rewrite old evidence")
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_NONAPPEND_HISTORY"):
            inspect(self.repo, self.old_raw, encode(self.new))

    def test_wrong_parent_bytes_rejected(self):
        with self.assertRaisesRegex(RetentionHold, "INCREMENT_PARENT_MANIFEST_MISMATCH"):
            lineage(self.old_raw + b"\n", encode(self.new))


class ActualManifestLineageTests(unittest.TestCase):
    def test_pinned_35_to_52_manifest_lineage(self):
        docs = Path(__file__).resolve().parents[2] / "docs"
        old = (docs / "P0_569_PINNED_35_HISTORY_BLOBS_SHA256_2026_11_24.json").read_bytes()
        new = (docs / "P0_569_PINNED_52_HISTORY_BLOBS_SHA256_2026_11_24.json").read_bytes()
        _, current, a, b, added, novel = lineage(old, new)
        self.assertEqual((len(a), len(b), len(added), len(novel)), (35, 52, 17, 9))
        self.assertEqual(current["source_unique_git_blobs"], 31)
        self.assertEqual(current["compressed_bytes_sum"], 185054)
        self.assertEqual(current["source_main_sha"], "6c4c5166c155c633dc09411006640e401cb29452")
        self.assertFalse(current["remote_archive_copy_confirmed"])


if __name__ == "__main__":
    unittest.main()
