import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import timedelta
from ops.v24_shadow_runner import tick,freeze,init,reserve,health,enc,sha
from ops.v22_forward_ledger import open_ledger
from ops.tests.test_v6_forward_bundle import inputs,NOW
from ops.tests.test_v6_forward_comparison import inputs as comparison_inputs

class ShadowRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"ledger.sqlite"
        self.db=open_ledger(self.path);self.addCleanup(self.db.close)
        self.cal=enc(comparison_inputs()[1]);self.raw=enc(inputs()["bl1"])
        self.calls=0
    def produce(self):
        self.calls+=1;return self.raw
    def no_network(self,*a,**k):raise AssertionError("UNEXPECTED_NETWORK")
    def tick(self):
        return tick(self.db,self.cal,sha(self.cal),producer=self.produce,capture_fn=self.no_network,now_fn=lambda:NOW)
    def test_end_to_end_and_throttle(self):
        a=self.tick()
        self.assertEqual(a["tasks"]["forecast"]["state"],"SEALED")
        self.assertEqual(a["ledger"]["unique_fixture_count"],1)
        self.assertEqual(a["verified_forward_sample_credit"],0)
        b=self.tick()
        self.assertEqual(b["tasks"]["forecast"]["state"],"THROTTLED")
        self.assertEqual(b["tasks"]["settlement"]["state"],"THROTTLED")
        self.assertEqual(self.calls,1)
    def test_restart_budget_and_incomplete_attempt(self):
        init(self.db);reserve(self.db,"forecast",NOW)
        db=open_ledger(self.path)
        try:
            self.assertEqual(health(db,NOW)["forecast"]["state"],"INCOMPLETE_ATTEMPT")
            self.assertIsNone(reserve(db,"forecast",NOW+timedelta(hours=1)))
            with self.assertRaisesRegex(ValueError,"CLOCK_REVERSED"):
                reserve(db,"forecast",NOW-timedelta(seconds=1))
        finally:db.close()
    def test_bad_calibration_before_attempt(self):
        with self.assertRaisesRegex(ValueError,"CALIBRATION_DIGEST"):
            tick(self.db,self.cal,"0"*64,producer=self.produce,now_fn=lambda:NOW)
        self.assertEqual(self.calls,0)
    def test_native_failure_throttled(self):
        def failure():raise OSError("offline")
        a=tick(self.db,self.cal,sha(self.cal),producer=failure,capture_fn=self.no_network,now_fn=lambda:NOW)
        self.assertEqual(a["tasks"]["forecast"]["state"],"HOLD_FORECAST_FAILED")
        self.assertEqual(self.tick()["tasks"]["forecast"]["state"],"THROTTLED")
        self.assertEqual(self.calls,0)
