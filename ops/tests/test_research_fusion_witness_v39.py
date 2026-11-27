import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from ops.tests.test_research_prospective_fusion_v38 import example,raw,NOW
from ops.research_prospective_fusion_v38 import capture,sha
from ops.research_fusion_witness_v39 import verify,certificate,SUBJECT

PINS=dict(source_sha="a"*40,workflow_sha="b"*40,run_id="123",attempt="1",as_of="2026-11-28T12:06:00Z")
def fixture():
    b=raw(example());r=raw(capture(b,as_of=NOW));bundle={"test_bundle":True}
    cert=certificate(PINS["source_sha"],PINS["workflow_sha"],PINS["run_id"],PINS["attempt"])
    output=[{"attestation":{"bundle":bundle},"verificationResult":{
        "mediaType":"application/vnd.dev.sigstore.verificationresult+json;version=0.1",
        "signature":{"certificate":cert},
        "verifiedTimestamps":[{"type":"Tlog","uri":"https://rekor.sigstore.dev","timestamp":"2026-11-28T12:01:00Z"}],
        "statement":{"_type":"https://in-toto.io/Statement/v1","predicateType":"https://slsa.dev/provenance/v1",
                     "subject":[{"name":SUBJECT,"digest":{"sha256":sha(r)}}]}}}]
    return b,r,raw(bundle),output
class FusionWitnessTests(unittest.TestCase):
    def run_case(self,change=None,returncode=0):
        b,r,bundle,o=fixture()
        if change:change(o[0]["verificationResult"])
        with patch("ops.research_fusion_witness_v39.subprocess.run",return_value=SimpleNamespace(returncode=returncode,stdout=raw(o))) as cli:
            result=verify(b,r,bundle,**PINS)
            self.assertTrue(cli.called)
            return result
    def test_valid_mocked_witness(self):
        r=self.run_case()
        self.assertTrue(r["observed_before_recorded_kickoff"])
        self.assertFalse(r["actual_kickoff_authenticated"])
        self.assertEqual(r["authenticated_samples"],0)
    def test_cli_rejection(self):
        self.assertFalse(self.run_case(returncode=1)["verification_completed"])
    def test_wrong_workflow(self):
        self.assertFalse(self.run_case(lambda r:r["signature"]["certificate"].update(buildSignerURI="other"))["verification_completed"])
    def test_wrong_receipt_digest(self):
        self.assertFalse(self.run_case(lambda r:r["statement"]["subject"][0]["digest"].update(sha256="0"*64))["verification_completed"])
    def test_late_witness(self):
        self.assertFalse(self.run_case(lambda r:r["verifiedTimestamps"][0].update(timestamp="2026-11-28T12:05:01Z"))["verification_completed"])
    def test_future_witness(self):
        self.assertFalse(self.run_case(lambda r:r["verifiedTimestamps"][0].update(timestamp="2026-11-28T12:06:01Z"))["verification_completed"])
    def test_wrong_tlog(self):
        self.assertFalse(self.run_case(lambda r:r["verifiedTimestamps"][0].update(uri="https://example.com"))["verification_completed"])
    def test_input_tamper_before_cli(self):
        b,r,bundle,_=fixture();d=example();d["history"][0]["score"]=[9,1]
        with patch("ops.research_fusion_witness_v39.subprocess.run") as cli:
            self.assertFalse(verify(raw(d),r,bundle,**PINS)["verification_completed"])
            cli.assert_not_called()
