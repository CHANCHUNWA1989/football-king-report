"""Local real Git tests for the pinned source tree read-only rehash."""
import copy
import gzip
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from ops.pinned_history_tree_rehash import verify
from ops.history_blob_retention_preflight import RetentionHold


class PinnedHistoryTreeRehashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic fixture")
        self.git("config", "user.email", "synthetic@example.invalid")
        self.git("commit", "--allow-empty", "-qm", "base")
        base = self.git("rev-parse", "HEAD")
        rows = []
        for i in range(2):
            path = f"history/test-{i}.json.gz"
            raw = gzip.compress(b'{"synthetic":true}', mtime=0)
            p = self.repo/path
            p.parent.mkdir(exist_ok=True)
            p.write_bytes(raw)
            self.git("add", path)
            oid = self.git("hash-object", path)
            rows.append(dict(path=path, git_blob_sha1=oid, compressed_bytes=len(raw),
                             prior_sha256_compressed=hashlib.sha256(raw).hexdigest() if i == 0 else None))
        self.git("commit", "-qm", "source")
        self.manifest = dict(schema="football-king-pinned-history-tree-inventory-v1",
            source_repo="CHANCHUNWA1989/football-king-report",
            source_main_sha=self.git("rev-parse", "HEAD"), archive_bootstrap_sha=base,
            archive_write_authorized=False, remote_archive_copy_confirmed=False,
            production_recommendations="DISABLED", records=rows,
            history_added_count=2, unique_git_blobs=1,
            compressed_bytes_sum=sum(r["compressed_bytes"] for r in rows))

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def test_pinned_source_readback_never_authorizes_write(self):
        before = self.git("rev-parse", "HEAD")
        result = verify(self.repo, self.manifest)
        self.assertEqual(result["source_paths_rehashed"], 2)
        self.assertEqual(result["unique_blobs"], 1)
        self.assertEqual(result["source_sha256_records"][0]["sha256_compressed"],
                         result["source_sha256_records"][1]["sha256_compressed"])
        self.assertFalse(result["archive_write_authorized"])
        self.assertFalse(result["remote_archive_copy_confirmed"])
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_missing_path_rejected_even_with_adjusted_counts(self):
        m = copy.deepcopy(self.manifest)
        m["records"].pop()
        m["history_added_count"] = 1
        m["compressed_bytes_sum"] = m["records"][0]["compressed_bytes"]
        with self.assertRaisesRegex(RetentionHold, "INCOMPLETE"):
            verify(self.repo, m)

    def test_wrong_digest_or_identity_rejected(self):
        for field, val in (("prior_sha256_compressed", "a"*64), ("git_blob_sha1", "b"*40)):
            m = copy.deepcopy(self.manifest)
            m["records"][0][field] = val
            with self.assertRaises(RetentionHold):
                verify(self.repo, m)

    def test_dirty_worktree_not_read(self):
        (self.repo/self.manifest["records"][0]["path"]).write_bytes(b"tampered")
        self.assertEqual(verify(self.repo, self.manifest)["source_paths_rehashed"], 2)
