"""Synthetic control-flow tests; mocks do not verify a real signature."""
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops.tests.test_research_forecast_proof_locator_v19 import fixture
from ops.research_forecast_archive_reverify_v20 import audit_run,read_members
REL="2026/11/01/123-1"
SOURCE="1"*40
WORKFLOW="2"*40

class ArchiveReverifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.dir=self.root/REL;self.dir.mkdir(parents=True)
        self.raw,p=fixture()
        self.files={"paired.json":json.dumps(p).encode(),"shadow.json":b"{}",
                    "slate.json":b"{}","research.sigstore.json":b"{}"}
        for n,b in self.files.items():(self.dir/(n+".gz")).write_bytes(gzip.compress(b))
    def run_audit(self):
        return audit_run(self.raw,self.root,REL,source_sha=SOURCE,workflow_sha=WORKFLOW)
    def mock_result(self):
        hashes={n:hashlib.sha256(b).hexdigest() for n,b in self.files.items()}
        return dict(audit_completed=True,signature_identity_and_subjects_verified=True,
                    production_recommendations="DISABLED",source_commit=SOURCE,
                    workflow_commit=WORKFLOW,run_id="123",run_attempt="1",
                    subject_sha256={n:hashes[n] for n in ("paired.json","shadow.json","slate.json")},
                    bundle_sha256=hashes["research.sigstore.json"],verified_tlog_utc="2026-11-01T14:10:00Z",
                    cases=[dict(pair_index=0,case_id="synthetic",observed_before_recorded_kickoff=True,
                                verified_tlog_utc="2026-11-01T14:10:00Z")])
    def test_binding_control_flow(self):
        with patch("ops.research_forecast_archive_reverify_v20.verify_cli",return_value=self.mock_result()):
            r=self.run_audit()
        self.assertTrue(r["audit_completed"])
        self.assertEqual(r["witness_before_recorded_kickoff_count"],1)
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["actual_kickoff_authenticated"])
    def test_wrong_subject_digest(self):
        m=self.mock_result();m["subject_sha256"]["paired.json"]="0"*64
        with patch("ops.research_forecast_archive_reverify_v20.verify_cli",return_value=m):
            self.assertFalse(self.run_audit()["audit_completed"])
    def test_wrong_run(self):
        m=self.mock_result();m["run_id"]="456"
        with patch("ops.research_forecast_archive_reverify_v20.verify_cli",return_value=m):
            self.assertFalse(self.run_audit()["audit_completed"])
    def test_missing_member(self):
        (self.dir/"shadow.json.gz").unlink()
        with patch("ops.research_forecast_archive_reverify_v20.verify_cli") as verify:
            self.assertFalse(self.run_audit()["audit_completed"])
            verify.assert_not_called()
    def test_symlink_and_traversal(self):
        p=self.dir/"shadow.json.gz";p.unlink();p.symlink_to(self.dir/"paired.json.gz")
        with self.assertRaises(ValueError):read_members(self.root,REL)
        with self.assertRaises(ValueError):read_members(self.root,"../"+REL)
    def test_cli_failure(self):
        with patch("ops.research_forecast_archive_reverify_v20.verify_cli",side_effect=ValueError("failed")):
            self.assertFalse(self.run_audit()["audit_completed"])
