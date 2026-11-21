"""Strict synthetic archive tamper tests. Actual GitHub bytes tested by CI."""
import copy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ops.archived_forward_model_coverage import audit_day, MAX_DECODED

NAME = "12345678-1.json.gz"


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()


def row():
    return {
        "production_recommendations": "DISABLED",
        "model": [.5, .3, .2],
        "market": [.45, .35, .2],
        "ab": [.5, .3, .2],
        "ab_model": "probability-shrink-to-uniform-fixed-0.15-v1",
        "c": [.5, .3, .2],
        "c_model": "market-anchored-fixed-25pct-model-75pct-consensus-v1",
    }


def fake_manifest():
    return {
        "schema": "football-king-pinned-forward-pair-day-v1",
        "source_commit": "a" * 40,
        "day": "2026/11/15",
        "production_recommendations": "DISABLED",
        "files": [],
    }


class ArchivedForwardAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.day = self.root / "2026" / "11" / "15"
        self.day.mkdir(parents=True)
        self.payload = {"comparisons": [row()], "production_recommendations": "DISABLED"}
        self.manifest = fake_manifest()

    def _inspect(self, *, raw=None, payload=None, edit_blob=True):
        if payload is None:
            payload = self.payload
        if raw is None:
            raw = gzip.compress(json.dumps(payload).encode(), mtime=0)
        (self.day / NAME).write_bytes(raw)
        self.manifest["files"] = [{
            "filename": NAME, "size_bytes": len(raw),
            "git_blob_sha1": blob(raw) if edit_blob else "b" * 40,
        }]
        return audit_day(json.dumps(self.manifest).encode(), self.root)

    def test_valid_original_A_is_still_not_penaltyblog_pair(self):
        r = self._inspect()
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["pinned_archive_files"], 1)
        self.assertTrue(r["pinned_git_blob_bytes_consistent"])
        self.assertEqual(r["legacy_A_model_vector_candidates_unverified"], 1)
        self.assertEqual(r["legacy_AB_shrinkage_candidates_not_penaltyblog"], 1)
        self.assertEqual(r["legacy_C_market_anchor_candidates_not_penaltyblog"], 1)
        self.assertEqual(r["native_penaltyblog_model_outputs_observed"], 0)
        self.assertEqual(r["validated_penaltyblog_pre_match_pairs"], 0)
        self.assertFalse(r["external_timestamp_verified"])
        self.assertFalse(r["publisher_identity_verified"])
        self.assertEqual(r["certified_prospective_samples"], 0)
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_altered_compressed_blob_rejected(self):
        self.assertEqual(self._inspect(edit_blob=False)["reason"],
                         "PINNED_ARCHIVE_GIT_BLOB_MISMATCH")

    def test_boolean_model_score_rejected(self):
        self.payload["comparisons"][0]["model"] = [True, 0, 0]
        self.assertEqual(self._inspect()["reason"], "INVALID_LEGACY_MODEL_VECTOR")

    def test_boolean_market_probability_rejected(self):
        self.payload["comparisons"][0]["market"] = [True, 0, 0]
        self.assertEqual(self._inspect()["reason"], "INVALID_LEGACY_MARKET_VECTOR")

    def test_false_penaltyblog_label_rejected(self):
        self.payload["comparisons"][0]["c_model"] = "penaltyblog-dixon-coles"
        self.assertEqual(self._inspect()["reason"], "UNKNOWN_OR_SPOOFED_CHALLENGER")

    def test_injected_penaltyblog_history_rejected(self):
        self.payload["comparisons"][0]["penaltyblog_poisson"] = [0.2, 0.3, 0.5]
        self.assertEqual(self._inspect()["reason"],
                         "LEGACY_ARCHIVE_PENALTYBLOG_FIELD_INJECTION")

    def test_fake_approved_model_injection_does_not_promote(self):
        self.payload["comparisons"][0]["eligible_for_model_scoring"] = True
        r = self._inspect()
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r.get("external_timestamp_verified", True))
        self.assertEqual(r["validated_penaltyblog_pre_match_pairs"], 0)

    def test_production_enabled_archive_rejected(self):
        self.payload["production_recommendations"] = "ENABLED"
        self.assertEqual(self._inspect()["reason"], "INVALID_OR_UNSAFE_ARCHIVED_BATCH")

    def test_production_enabled_row_rejected(self):
        self.payload["comparisons"][0]["production_recommendations"] = "ENABLED"
        self.assertEqual(self._inspect()["reason"], "INVALID_OR_UNSAFE_ARCHIVED_ROW")

    def test_zipbomb_expansion_limit(self):
        raw = gzip.compress(b"Z" * (MAX_DECODED + 1), mtime=0)
        self.assertEqual(self._inspect(raw=raw)["reason"], "ARCHIVE_EXPANSION_LIMIT")

    def test_invalid_gzip_rejected(self):
        self.assertEqual(self._inspect(raw=b"randombytes")["reason"],
                         "INVALID_ARCHIVED_GZIP_OR_JSON")

    def test_bad_manifest_file_path(self):
        raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        self.manifest["files"] = [{
            "filename": "../secret.json.gz", "size_bytes": len(raw),
            "git_blob_sha1": blob(raw),
        }]
        r = audit_day(json.dumps(self.manifest).encode(), self.root)
        self.assertEqual(r["reason"], "INVALID_OR_DUPLICATE_ARCHIVE_NAME")

    def test_absent_file_rejected(self):
        raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        self.manifest["files"] = [{
            "filename": NAME, "size_bytes": len(raw),
            "git_blob_sha1": blob(raw),
        }]
        r = audit_day(json.dumps(self.manifest).encode(), self.root)
        self.assertEqual(r["status"], "HOLD")
        self.assertNotIn("pinned_git_blob_bytes_consistent", r)

    def test_symlink_rejected(self):
        raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        real = self.root / "outside.gz"
        real.write_bytes(raw)
        (self.day / NAME).symlink_to(real)
        self.manifest["files"] = [{
            "filename": NAME, "size_bytes": len(raw),
            "git_blob_sha1": blob(raw),
        }]
        self.assertEqual(audit_day(json.dumps(self.manifest).encode(), self.root)["reason"],
                         "SYMLINK_ARCHIVE_NOT_ALLOWED")

    def test_duplicate_json_key_rejected(self):
        raw = gzip.compress(b'{"comparisons":[],"comparisons":[]}', mtime=0)
        self.assertEqual(self._inspect(raw=raw)["reason"], "DUPLICATE_JSON_KEY")

    def test_no_partial_success_if_second_file_missing(self):
        raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        (self.day / NAME).write_bytes(raw)
        self.manifest["files"] = [
            {"filename": NAME, "size_bytes": len(raw), "git_blob_sha1": blob(raw)},
            {"filename": "12345679-1.json.gz", "size_bytes": len(raw),
             "git_blob_sha1": blob(raw)},
        ]
        r = audit_day(json.dumps(self.manifest).encode(), self.root)
        self.assertEqual(r["status"], "HOLD")
        self.assertNotIn("pinned_git_blob_bytes_consistent", r)

    def test_manifest_duplicate_filename_rejected(self):
        raw = gzip.compress(json.dumps(self.payload).encode(), mtime=0)
        (self.day / NAME).write_bytes(raw)
        entry = {"filename": NAME, "size_bytes": len(raw), "git_blob_sha1": blob(raw)}
        self.manifest["files"] = [entry, copy.deepcopy(entry)]
        self.assertEqual(audit_day(json.dumps(self.manifest).encode(), self.root)["reason"],
                         "INVALID_OR_DUPLICATE_ARCHIVE_NAME")

    def test_invalid_calendar_date_rejected(self):
        self.manifest["day"] = "2026/02/31"
        self.assertEqual(audit_day(json.dumps(self.manifest).encode(), self.root)["reason"],
                         "day is out of range for month")


if __name__ == "__main__":
    unittest.main()
