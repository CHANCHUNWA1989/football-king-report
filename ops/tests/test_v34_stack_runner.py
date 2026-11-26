import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import timedelta
from ops.v34_stack_runner import tick,preflight,settle_due
from ops.v32_stack_ledger import open_ledger,register,report
from ops.v27_stack_archive import seal,enc,sha
from ops.tests.test_v27_stack_archive import inputs
from ops.tests.test_v6_forward_comparison import NOW,KO,result
from ops.v9_stacking_research import TRAIN,CAL,EXPERTS
from ops.v8_multiseason import PIN
from ops.v21_raw_results import URLS

def sample():
    a,b=inputs()
    for k in ("portable","native_feature","prefix"):
        a[k+"_parity_n"]=205;a[k+"_max_abs_error"]=0.
    a["model"].update(historical_source_commit=PIN,training_seasons=list(TRAIN),calibration_season=CAL,status="HOLD",production_recommendations="DISABLED",verified_forward_sample_credit=0)
    a["de1_prior_tail"]=[{"date":"2026-05-01","y":i%3,"experts":{k:[.5,.3,.2] for k in EXPERTS}} for i in range(192)]
    exp=enc(a)
    return exp,seal(exp,enc(b),NOW)
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"stack.sqlite";self.db=open_ledger(self.path)
        self.addCleanup(lambda:self.db.close());self.exp,self.raw=sample()
        self.calls=0;self.obs=KO+timedelta(hours=3)
    def producer(self,*a,**k):
        self.calls+=1;return self.raw
    def no_network(self,*a,**k):raise AssertionError("UNEXPECTED_NETWORK")
    def capture(self,provider,year):
        raw=enc(result())
        return raw,{"provider":provider,"season":year,"source":URLS[provider]+str(year),"captured_utc":self.obs.isoformat(),"sha256":sha(raw),"bytes":len(raw),"source_authenticated":False}
    def test_restart_preserves_throttle(self):
        q=tick(self.db,self.exp,sha(self.exp),producer=self.producer,capture_fn=self.no_network,clock_fn=lambda:NOW)
        self.assertEqual(q["ledger"]["unique_fixture_count"],1)
        self.assertEqual(q["tasks"]["forecast"]["state"],"SEALED")
        self.db.close();self.db=open_ledger(self.path)
        q=tick(self.db,self.exp,sha(self.exp),producer=self.no_network,capture_fn=self.no_network,clock_fn=lambda:NOW)
        self.assertTrue(all(v["state"]=="THROTTLED" for v in q["tasks"].values()))
        self.assertEqual(self.calls,1)
    def test_bad_export_no_calls(self):
        with self.assertRaisesRegex(ValueError,"EXPORT_DIGEST"):
            tick(self.db,self.exp,"0"*64,producer=self.producer,clock_fn=lambda:NOW)
        self.assertEqual(self.calls,0)
    def test_due_only_and_settlement(self):
        register(self.db,self.raw,sha(self.raw),NOW)
        self.assertEqual(settle_due(self.db,capture_fn=self.no_network,clock_fn=lambda:NOW)["requests"],0)
        q=settle_due(self.db,capture_fn=self.capture,clock_fn=lambda:self.obs)
        self.assertEqual(q["newly_settled"],1)
        self.assertEqual(report(self.db)["settled_count"],1)
        self.assertEqual(settle_due(self.db,capture_fn=self.no_network,clock_fn=lambda:self.obs)["requests"],0)
    def test_failed_source_remains_pending(self):
        register(self.db,self.raw,sha(self.raw),NOW)
        def fail(*a):raise OSError("offline")
        q=settle_due(self.db,capture_fn=fail,clock_fn=lambda:self.obs)
        self.assertEqual(q["reasons"],{"SOURCE_UNAVAILABLE_OR_INVALID":1})
        self.assertEqual(report(self.db)["pending_count"],1)

    def test_model_digest_is_frozen_across_restart(self):
        import json
        tick(self.db,self.exp,sha(self.exp),producer=self.producer,capture_fn=self.no_network,clock_fn=lambda:NOW)
        altered=json.loads(self.exp);altered["model"]["intercept"][0]=.01;raw=enc(altered)
        with self.assertRaisesRegex(ValueError,"COHORT_MODEL_CHANGED"):
            tick(self.db,raw,sha(raw),producer=self.no_network,capture_fn=self.no_network,clock_fn=lambda:NOW)
