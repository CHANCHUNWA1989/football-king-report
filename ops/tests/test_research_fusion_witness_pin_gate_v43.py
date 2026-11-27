import unittest
from copy import deepcopy
from unittest.mock import patch
from ops.research_fusion_witness_pin_gate_v43 import resolve,verify_with_fresh_pins,REPO,WORKFLOW

ARGS=dict(run_id="123",attempt="1",as_of="2026-11-28T12:10:00Z")
SHA="a"*40
def meta():
    repo=dict(id=1411226578,full_name=REPO,owner=dict(id=339931460))
    return dict(id=123,run_attempt=1,path=WORKFLOW,head_branch="main",event="workflow_dispatch",
                status="completed",conclusion="success",referenced_workflows=[],
                repository=deepcopy(repo),head_repository=deepcopy(repo),head_sha=SHA,
                run_started_at="2026-11-28T12:00:00Z",updated_at="2026-11-28T12:05:00Z")
def witness():
    return dict(verification_completed=True,observed_before_recorded_kickoff=True,
                source_commit=SHA,workflow_commit=SHA,run_id="123",run_attempt="1",
                verified_tlog_utc="2026-11-28T12:01:00Z")
class PinGateTests(unittest.TestCase):
    def test_pins(self):
        p=resolve(meta(),**ARGS)
        self.assertEqual(p["source_sha"],SHA)
        self.assertEqual(p["workflow_sha"],SHA)
    def test_wrong_run_or_attempt(self):
        for key,value in (("id",124),("run_attempt",2)):
            m=meta();m[key]=value
            with self.assertRaises(ValueError):resolve(m,**ARGS)
    def test_wrong_workflow_or_reusable(self):
        for key,value in (("path","other.yml"),("referenced_workflows",[{}]),("head_branch","other"),("event","push")):
            m=meta();m[key]=value
            with self.assertRaises(ValueError):resolve(m,**ARGS)
    def test_wrong_owner_or_repository(self):
        for name in ("repository","head_repository"):
            m=meta();m[name]["owner"]["id"]=2
            with self.assertRaises(ValueError):resolve(m,**ARGS)
    def test_future_or_failed(self):
        for key,value in (("updated_at","2026-11-28T12:11:00Z"),("conclusion","failure")):
            m=meta();m[key]=value
            with self.assertRaises(ValueError):resolve(m,**ARGS)
    def run_gate(self,m,v):
        with patch("ops.research_fusion_witness_pin_gate_v43.metadata",return_value=m),patch("ops.research_fusion_witness_pin_gate_v43.verify",return_value=v) as cli:
            r=verify_with_fresh_pins(b"raw",b"receipt",b"bundle",**ARGS)
            return r,cli
    def test_mock_success_never_promotes(self):
        r,cli=self.run_gate(meta(),witness())
        self.assertTrue(r["witness_verified"])
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["model_promotion_allowed"])
        self.assertEqual(cli.call_args.kwargs["workflow_sha"],SHA)
    def test_metadata_rejected_before_verification(self):
        r,cli=self.run_gate({},witness())
        self.assertFalse(r["metadata_resolved"])
        cli.assert_not_called()
    def test_witness_mismatch_or_time(self):
        for key,value in (("source_commit","b"*40),("run_attempt","2"),
                          ("verified_tlog_utc","2026-11-28T12:06:00Z"),("verification_completed",False)):
            v=witness();v[key]=value
            r,_=self.run_gate(meta(),v)
            self.assertFalse(r["witness_verified"])
