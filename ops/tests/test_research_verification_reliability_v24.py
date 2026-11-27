import unittest
from pathlib import Path
from unittest.mock import patch
from ops.tests.test_research_forecast_batch_v22 import loc,result
from ops.research_forecast_batch_v22 import batch
from ops.research_forecast_archive_reverify_v20 import VerificationFailure

class VerificationReliabilityTests(unittest.TestCase):
    def test_retry_can_recover(self):
        calls={}
        def run(raw,root,path):
            calls[path]=calls.get(path,0)+1
            if path=="one" and calls[path]==1:
                return dict(archive_run=path,state="AUDIT_REJECTED",reason="ATTESTATION_CLI_REJECTED",cases=[],source_commit="a",workflow_commit="b")
            return dict(result(raw,root,path),source_commit="a",workflow_commit="b")
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=run):
            r=batch(b"test",Path("."),loc())
        self.assertTrue(r["batch_passed"])
        self.assertEqual(r["retry_count"],1)
        self.assertEqual(r["unique_witness_before_recorded_kickoff_count"],1)
    def test_explicit_certificate_failure_not_retried(self):
        def run(raw,root,path):
            return dict(archive_run=path,state="AUDIT_REJECTED",reason="CERTIFICATE_IDENTITY_MISMATCH",cases=[])
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=run) as m:
            r=batch(b"test",Path("."),loc())
        self.assertFalse(r["batch_passed"])
        self.assertEqual(m.call_count,2)
    def test_retry_pin_change_rejected(self):
        calls={}
        def run(raw,root,path):
            calls[path]=calls.get(path,0)+1
            if calls[path]==1:
                return dict(archive_run=path,state="AUDIT_REJECTED",reason="ATTESTATION_CLI_REJECTED",cases=[],source_commit="a",workflow_commit="b")
            return dict(result(raw,root,path),source_commit="changed",workflow_commit="b")
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=run):
            r=batch(b"test",Path("."),loc())
        self.assertFalse(r["batch_passed"])
        self.assertEqual(r["run_states"],{"RETRY_PIN_MISMATCH":2})
    def test_repeated_failure_stays_failed(self):
        def run(raw,root,path):
            return dict(archive_run=path,state="AUDIT_REJECTED",reason="ATTESTATION_CLI_REJECTED",cases=[],source_commit="a",workflow_commit="b")
        with patch("ops.research_forecast_batch_v22.run_one",side_effect=run):
            r=batch(b"test",Path("."),loc())
        self.assertFalse(r["batch_passed"])
        self.assertEqual(r["retry_count"],2)
        self.assertEqual(r["authenticated_samples"],0)
    def test_safe_failure_reason(self):
        self.assertEqual(VerificationFailure("private raw stderr").reason,"FRESH_VERIFICATION_FAILED")
        self.assertEqual(VerificationFailure("CERTIFICATE_IDENTITY_MISMATCH").reason,"CERTIFICATE_IDENTITY_MISMATCH")
