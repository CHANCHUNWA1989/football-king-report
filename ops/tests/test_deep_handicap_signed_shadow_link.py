"""Mocked verifier boundary tests only; no real attestation is claimed."""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from deep_handicap_signed_shadow_link import audit
from test_deep_handicap_input_reconstruction import packed,pins,encode
from test_deep_handicap_private_capture import NOW


class SignedShadowLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof=Path(self.temp.name)
        self.raw,_,_=packed()
        (self.proof/"shadow.json").write_bytes(self.raw[0])
        self.verified={"audit_completed":True,"signature_identity_and_subjects_verified":True,
                       "subject_sha256":{"shadow.json":hashlib.sha256(self.raw[0]).hexdigest()},
                       "verified_tlog_utc":(NOW-timedelta(minutes=1)).isoformat()}

    def call(self,**kwargs):
        args=dict(pins=pins(self.raw),expected_capture_utc=NOW.isoformat(),
                  source_sha="a"*40,workflow_sha="b"*40,run_id="123",attempt="1",
                  now=NOW+timedelta(hours=3))
        args.update(kwargs)
        return audit(self.proof,self.raw[1],self.raw[2],**args)

    def test_fresh_verifier_link_does_not_certify_dhe(self):
        with patch("deep_handicap_signed_shadow_link.provenance.audit",return_value=self.verified) as verifier:
            r=self.call()
        verifier.assert_called_once_with(self.proof,source_sha="a"*40,workflow_sha="b"*40,
                                        run_id="123",attempt="1",now=NOW+timedelta(hours=3))
        self.assertTrue(r["shadow_signature_verified"])
        self.assertTrue(r["shadow_subject_bytes_matched"])
        self.assertTrue(r["shadow_witness_before_candidate_cutoff"])
        self.assertTrue(r["candidate_formula_reconstruction_matched"])
        self.assertFalse(r["candidate_independent_witness_verified"])
        self.assertFalse(r["quote_independent_witness_verified"])
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertNotIn("decimal_odds",json.dumps(r))

    def test_saved_report_is_not_accepted_by_real_verifier(self):
        (self.proof/"shadow.verification.json").write_bytes(encode(self.verified))
        # Missing real signed subjects and bundle; no network verification.
        r=self.call()
        self.assertEqual(r["reason"],"SHADOW_ATTESTATION_NOT_VERIFIED")
        self.assertFalse(r["shadow_signature_verified"])

    def test_late_witness_and_modified_shadow_bytes(self):
        self.verified["verified_tlog_utc"]=(NOW+timedelta(seconds=1)).isoformat()
        with patch("deep_handicap_signed_shadow_link.provenance.audit",return_value=self.verified):
            self.assertEqual(self.call()["reason"],"SHADOW_WITNESS_AFTER_CANDIDATE_CUTOFF")
        (self.proof/"shadow.json").write_bytes(self.raw[0]+b" ")
        with patch("deep_handicap_signed_shadow_link.provenance.audit",return_value=self.verified):
            self.assertEqual(self.call()["reason"],"SIGNED_SHADOW_BYTES_CHANGED")

    def test_failed_signature_and_wrong_input_pin(self):
        with patch("deep_handicap_signed_shadow_link.provenance.audit",return_value={"audit_completed":False}):
            self.assertFalse(self.call()["candidate_formula_reconstruction_matched"])
        with patch("deep_handicap_signed_shadow_link.provenance.audit",return_value=self.verified):
            r=self.call(pins={**pins(self.raw),"quote_report":"0"*64})
        self.assertTrue(r["shadow_signature_verified"])
        self.assertFalse(r["candidate_formula_reconstruction_matched"])
        self.assertEqual(r["reason"],"DHE_FORMULA_RECONSTRUCTION_REJECTED")
