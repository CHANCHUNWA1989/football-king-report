"""Offline qualification report consistency tests."""
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from run_qualification import finalize

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
if __name__=='__main__':unittest.main(verbosity=2)
