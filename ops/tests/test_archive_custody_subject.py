"""Actual local Git fixture tests for the unsigned custody subject."""
import gzip
import hashlib
import unittest
from ops.history_blob_retention_preflight import RetentionHold
from ops.archive_custody_subject import build, canonical
from ops.tests import test_thirteen_latest_reader_preflight as fixtures


class ArchiveCustodySubjectTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ThirteenLatestReaderTests("test_exact_13_read_and_stale_is_not_release")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root = self.case.root
        self.path = "history/2026/11/24/123-1.json.gz"
        self.raw = gzip.compress(b'{"synthetic":true}', mtime=0)
        self.put()
        self.source = self.case.commit()
        self.base = self.case.archive
        self.case.git("checkout", "--detach", self.base)
        self.put()
        self.candidate = self.case.commit()
        oid = hashlib.sha1(b"blob " + str(len(self.raw)).encode() + b"\0" + self.raw).hexdigest()
        self.manifest = dict(schema="football-king-pinned-history-tree-inventory-v1",
                             source_repo="CHANCHUNWA1989/football-king-report",
                             source_main_sha=self.source, archive_bootstrap_sha=self.base,
                             archive_write_authorized=False, remote_archive_copy_confirmed=False,
                             production_recommendations="DISABLED", history_added_count=1,
                             unique_git_blobs=1, compressed_bytes_sum=len(self.raw),
                             records=[dict(path=self.path, git_blob_sha1=oid, compressed_bytes=len(self.raw),
                                           prior_sha256_compressed=None)])

    def put(self):
        p = self.root / self.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.raw)

    def test_deterministic_subject_is_not_external_attestation(self):
        a = build(self.root, self.manifest, self.candidate)
        b = build(self.root, self.manifest, self.candidate)
        self.assertEqual(a, b)
        self.assertEqual(a["subject_sha256"], hashlib.sha256(canonical(a["subject"])).hexdigest())
        self.assertEqual(a["mutable_pointers"], 13)
        for flag in ("external_signature_verified", "trusted_timestamp_verified",
                     "independent_archive_retention_verified", "independent_review_verified",
                     "hosted_archive_write_authorized", "source_switch_authorized"):
            self.assertIs(a[flag], False)

    def test_unexpected_candidate_file_is_rejected(self):
        (self.root / "extra.txt").write_text("synthetic")
        with self.assertRaisesRegex(RetentionHold, "CANDIDATE_HAS_UNEXPECTED_DELTA"):
            build(self.root, self.manifest, self.case.commit())

    def test_changed_gzip_is_rejected(self):
        self.raw = gzip.compress(b'{"different":true}', mtime=0)
        self.put()
        with self.assertRaisesRegex(RetentionHold, "CANDIDATE_HISTORY_BYTES_MISMATCH"):
            build(self.root, self.manifest, self.case.commit())

    def test_mutable_pointer_replacement_is_rejected(self):
        self.case.git("checkout", self.source, "--", "sources/latest.json")
        with self.assertRaisesRegex(RetentionHold, "CANDIDATE_HAS_UNEXPECTED_DELTA"):
            build(self.root, self.manifest, self.case.commit())


if __name__ == "__main__":
    unittest.main()
