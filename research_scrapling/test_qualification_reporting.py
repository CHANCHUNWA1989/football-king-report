"""Offline qualification report consistency tests."""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from run_qualification import DOMAIN, finalize, validate_gate

class ReportTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)
    def verify(self,expected,raw=None,passed=True,offline=False,failed=False):
        if raw is not None:(self.path/'historical.json').write_bytes(raw)
        report={'status':'HOLD','live_trading':'DISABLED','production_recommendations':'DISABLED','model_input_allowed':False,'steps':[{'name':'single_probe','status':'PASS' if passed else 'SKIPPED_OFFLINE'}]}
        with redirect_stdout(io.StringIO()) as out:code=finalize(self.path,report,failed,offline)
        disk=json.loads((self.path/'qualification.json').read_text())
        logged=json.loads(out.getvalue().splitlines()[0].removeprefix('QUALIFICATION '))
        self.assertEqual(disk,logged);self.assertEqual(disk['qualification'],expected)
        self.assertEqual(code,int(expected=='FAILED'));self.assertFalse(disk['model_input_allowed'])
    def test_valid(self):self.verify('HISTORICAL_RESEARCH_PASS',b'{"status":"HOLD","live_trading":"DISABLED","production_recommendations":"DISABLED"}')
    def test_missing(self):self.verify('FAILED')
    def test_invalid(self):self.verify('FAILED',b'{')
    def test_oversize(self):self.verify('FAILED',b'x'*100001)
    def test_duplicate(self):self.verify('FAILED',b'{"status":"HOLD","status":"HOLD"}')
    def test_unsafe(self):self.verify('FAILED',b'{"status":"HOLD","live_trading":"ENABLED","production_recommendations":"DISABLED"}')
    def test_offline(self):self.verify('OFFLINE_ONLY_PASS',passed=False,offline=True)
    def test_previous_failure(self):self.verify('FAILED',passed=False,offline=True,failed=True)
    def test_actual_batch_schema_accepted(self):
        from unittest.mock import patch
        import football_batch as batch
        # Exercise the actual producer, not a hand-authored safety report.
        with patch.object(batch.p,"acquire",side_effect=TimeoutError):
            report=batch.run()
        self.assertEqual(report["error_type"],"TimeoutError")
        self.assertEqual(report["live_trading"],"DISABLED")
        self.assertFalse(report["model_input_allowed"])
        (self.path/"expanded.json").write_text(json.dumps(report))
        q={"steps":[{"name":"expanded_probe","status":"FAIL"}]}
        with redirect_stdout(io.StringIO()):
            code=finalize(self.path,q,True,False)
        self.assertEqual(code,1)
        self.assertEqual(q["artifact_validation_errors"],[])
        self.assertEqual(q["qualification"],"FAILED")
    def test_actual_batch_success_schema(self):
        from unittest.mock import patch
        import football_batch as batch
        rows=[{"status":"HISTORICAL_MATCH"} for _ in batch.EXPECTED]
        with patch.object(batch.p,"acquire",return_value=(b"{}",{})),patch.object(batch,"compare",return_value=rows):
            report=batch.run()
        self.assertEqual(report["matched"],report["expected"])
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["live_trading"],"DISABLED")
        self.assertFalse(report["model_input_allowed"])
        (self.path/"expanded.json").write_text(json.dumps(report))
        q={"steps":[{"name":"expanded_probe","status":"PASS"}]}
        with redirect_stdout(io.StringIO()):
            code=finalize(self.path,q,False,False)
        self.assertEqual(code,0)
        self.assertEqual(q["artifact_validation_errors"],[])
    def gate_doc(self):
        return dict(status="HOLD",live_trading="DISABLED",production_recommendations="DISABLED",model_input_allowed=False)
    def test_preflight_producer(self):
        from source_preflight import check, ROOT
        (self.path/"source-preflight.json").write_text(json.dumps(check(DOMAIN,ROOT/"disabled.json")))
        validate_gate(self.path,"source-preflight")
    def test_invalid_preflight_fields(self):
        valid=dict(self.gate_doc(),domain=DOMAIN,live_source_count=0,historical_only=True,independent_upstream_certified=False,historical_preflight_pass=True)
        for k,v in [("domain","wrong"),("live_source_count",False),("live_source_count",1),("historical_preflight_pass",False),("model_input_allowed",None),("independent_upstream_certified",True)]:
            with self.subTest(field=k,value=v):
                (self.path/"source-preflight.json").write_text(json.dumps(dict(valid,**{k:v})))
                with self.assertRaises(ValueError):validate_gate(self.path,"source-preflight")
    def test_disabled_gate(self):
        valid=dict(self.gate_doc(),research_only=True)
        (self.path/"disabled.json").write_text(json.dumps(valid))
        validate_gate(self.path,"disabled")
        for bad in [dict(valid,evidence=[]),dict(valid,research_only=1),self.gate_doc()]:
            (self.path/"disabled.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):validate_gate(self.path,"disabled")
    def test_disabled_missing_report(self):
        q={"steps":[{"name":"disabled_config","status":"PASS"}]}
        with redirect_stdout(io.StringIO()):self.assertEqual(finalize(self.path,q,False,True),1)
        self.assertIn("disabled",q["artifact_validation_errors"])
    def test_bad_gate_blocks_network(self):
        from unittest.mock import patch
        import run_qualification as runner
        steps=[("source_preflight",["source_preflight.py"]),("single_probe",["historical_probe.py"])]
        def fake_run(*args,**kwargs):
            from types import SimpleNamespace
            (self.path/"source-preflight.json").write_text(json.dumps(self.gate_doc()))
            return SimpleNamespace(returncode=0)
        with patch.object(runner,"STEPS",steps),patch.object(runner.sys,"argv",["runner","--output",str(self.path)]),patch.object(runner.subprocess,"run",side_effect=fake_run) as run,redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main(),1)
        self.assertEqual(run.call_count,1)
        q=json.loads((self.path/"qualification.json").read_text())
        self.assertEqual(q["steps"][0]["exit_code"],126)
        self.assertEqual(q["steps"][1]["status"],"SKIPPED_PREVIOUS_FAILURE")
if __name__=='__main__':unittest.main(verbosity=2)
