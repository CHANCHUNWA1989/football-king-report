"""Synthetic tamper, timing and fail-closed tests for fixed real 19-file seal."""
import copy
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops import identity_ab_sealed_archive_audit as check
from ops import identity_ab_forward_seal as seal
from ops.tests.test_identity_ab_forward_seal import report, SHA, RUN, ATTEMPT, NOW


class SealedArchiveReadOnlyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/check.RUN_DIRECTORY
        self.proof=report()
        self.index=seal.create_local_archive(
            self.root,self.proof,received_utc=NOW.isoformat(),
            source_commit=SHA,run_id=RUN,attempt=ATTEMPT)
        self.patches=patch.multiple(
            check, EXPECTED_SOURCE_COMMIT=SHA,
            EXPECTED_RAW_SHA256=self.proof["raw_source_sha256"],
            EXPECTED_INPUT_SHA256=self.proof["ab"]["input_canonical_sha256"],
            EXPECTED_LEGACY_BLOB_SHA1=self.proof["ab"]["frozen_legacy_source_blob_sha1"],
            EXPECTED_RECEIVED_UTC=NOW.isoformat(),
            EXPECTED_RECORD_COUNT=1,
            PINNED_INDEX_GIT_BLOB_SHA1=check._git_blob(
                (self.root/"index.json").read_bytes()))
        self.patches.start()
        self.addCleanup(self.patches.stop)

    def test_original_seal_passes_and_remains_completely_unscored(self):
        output=check.audit(self.root,as_of_utc="2026-11-08T01:00:00+00:00")
        self.assertEqual(output["forecast_file_count"],1)
        self.assertTrue(output["all_forecast_byte_pins_valid"])
        self.assertEqual(output["forecast_cohort"]["prediction_vectors_equal"],1)
        self.assertEqual(output["forecast_cohort"]["pending_before_scheduled_kickoff"],1)
        self.assertEqual(output["independent_regulation_ft_result_count"],0)
        self.assertEqual(output["scored_result_count"],0)
        self.assertFalse(output["model_uplift_proven"])
        self.assertFalse(output["positive_ev_verified"])
        self.assertEqual(output["production_recommendations"],"DISABLED")
        self.assertFalse(output["cases"][0]["eligible_for_scoring"])

    def test_elapsed_scheduled_kickoff_still_does_not_settle(self):
        output=check.audit(self.root,as_of_utc="2026-11-11T00:00:00+00:00")
        self.assertEqual(output["forecast_cohort"][
            "scheduled_kickoff_elapsed_no_independent_result"],1)
        self.assertEqual(output["cases"][0]["status"],
                         "AWAITING_INDEPENDENT_REGULATION_FT")
        self.assertEqual(output["scored_result_count"],0)

    def test_raw_forecast_single_bit_change_fails_against_index(self):
        path=self.root/"100075.json"
        data=path.read_bytes()
        path.write_bytes(data[:-2]+bytes([data[-2]^1])+data[-1:])
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "ARCHIVED_FORECAST_BYTES_CHANGED"):
            check.audit(self.root)

    def test_wrong_index_original_git_blob_fails(self):
        path=self.root/"index.json"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "PINNED_ARCHIVE_INDEX_CHANGED"):
            check.audit(self.root)

    def test_false_certification_rejected_even_if_all_hashes_replaced(self):
        path=self.root/"100075.json"
        case=json.loads(path.read_text())
        case["certified_case_count"]=1
        new=(json.dumps(case,sort_keys=True,separators=(",",":"),
                        ensure_ascii=False)+"\n").encode()
        path.write_bytes(new)
        index_path=self.root/"index.json"
        index=json.loads(index_path.read_text())
        index["record_sha256"]["100075.json"]=hashlib.sha256(new).hexdigest()
        index_path.write_text(
            json.dumps(index,sort_keys=True,separators=(",",":"),
                       ensure_ascii=False)+"\n")
        with patch.object(check, "PINNED_INDEX_GIT_BLOB_SHA1",
                          check._git_blob(index_path.read_bytes())):
            with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                        "ARCHIVED_UNTRUSTED_AUTHORITY"):
                check.audit(self.root)

    def test_changed_kickoff_horizon_rejected_even_if_file_sha_recomputed(self):
        path=self.root/"100075.json"
        case=json.loads(path.read_text())
        case["forecast_horizon_at_capture_minutes"]+=60
        data=(json.dumps(case,sort_keys=True,separators=(",",":"),
                         ensure_ascii=False)+"\n").encode()
        path.write_bytes(data)
        index_path=self.root/"index.json"
        index=json.loads(index_path.read_text())
        index["record_sha256"]["100075.json"]=hashlib.sha256(data).hexdigest()
        index_path.write_text(
            json.dumps(index,sort_keys=True,separators=(",",":"),
                       ensure_ascii=False)+"\n")
        with patch.object(check,"PINNED_INDEX_GIT_BLOB_SHA1",
                          check._git_blob(index_path.read_bytes())):
            with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                        "ARCHIVED_KICKOFF_OR_HORIZON_CHANGED"):
                check.audit(self.root)

    def test_extra_file_and_missing_file_both_refused(self):
        extra=self.root/"untracked.json"
        extra.write_text("{}")
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "ARCHIVE_EXTRA_OR_MISSING_FILE"):
            check.audit(self.root)
        extra.unlink()
        (self.root/"100075.json").unlink()
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "ARCHIVE_EXTRA_OR_MISSING_FILE"):
            check.audit(self.root)

    def test_symbolic_link_rejected(self):
        path=self.root/"100075.json"
        path.unlink()
        path.symlink_to(self.root/"index.json")
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "UNSAFE_ARCHIVED_FILE"):
            check.audit(self.root)

    def test_unexpected_run_directory_rejected(self):
        wrong=self.root.parent/"another-run"
        self.root.rename(wrong)
        with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                    "UNSAFE_ARCHIVE_DIRECTORY"):
            check.audit(wrong)

    def test_duplicate_json_keys_cannot_be_hidden_by_correct_hash(self):
        path=self.root/"100075.json"
        data=path.read_bytes().rstrip()
        corrupt=data[:-1]+b', "status":"SHADOW_ONLY_UNVERIFIED"}\n'
        path.write_bytes(corrupt)
        ix=self.root/"index.json"
        original=json.loads(ix.read_text())
        original["record_sha256"]["100075.json"]=hashlib.sha256(corrupt).hexdigest()
        ix.write_text(json.dumps(original,sort_keys=True,
                                 separators=(",",":"))+"\n")
        with patch.object(check,"PINNED_INDEX_GIT_BLOB_SHA1",
                          check._git_blob(ix.read_bytes())):
            with self.assertRaisesRegex(check.ForwardArchiveAuditError,
                                        "DUPLICATE_ARCHIVED_JSON_KEY"):
                check.audit(self.root)


if __name__=="__main__":
    unittest.main()
