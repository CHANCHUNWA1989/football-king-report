import unittest
from datetime import datetime,timedelta
from unittest.mock import patch
from ops.research_live_calibration_v8 import calibrate,legacy_readiness,score
from ops.tests.test_research_live_evidence_v3 import bundle,final,FIN,RELEASE
from ops.research_live_evidence_v3 import settle

class CalibrationTests(unittest.TestCase):
    def test_real_replay_insufficient(self):
        b=bundle(); r=settle(b,final(),as_of=FIN)
        out=calibrate([(b,r)],model_release=RELEASE,train_start="2026-11-27T00:00:00Z",
            train_cutoff="2026-11-27T10:00:00Z",test_end="2026-11-28T00:00:00Z",as_of="2026-11-29T00:00:00Z")
        self.assertEqual(out["train_n"],0)
        self.assertEqual(out["excluded"]["TRAIN_RESULT_NOT_AVAILABLE_BEFORE_CUTOFF"],1)
        self.assertFalse(out["weights_fitted"])
    def test_legacy(self):
        r=legacy_readiness({"schema":"football-king-forward-research-1","samples":[{}],"n":1})
        self.assertEqual(r["live_training_eligible_count"],0)
    def test_score(self):
        b=dict(home=.4,draw=.3,away=.3);d=dict(home=.8,draw=.1,away=.1)
        rows=[("a",b,d,"home","2026-11-01")]
        self.assertLess(score(rows,1)["log_loss"],score(rows,0)["log_loss"])
    def mock_pairs(self,y):
        base=datetime.fromisoformat("2026-10-01T00:00:00+00:00")
        rows=[]
        for i in range(40):
            t=base+timedelta(days=i,hours=10)
            b=dict(event_id=str(i),model_release="mock",as_of=t.isoformat(),
                   report=dict(minute=25,baseline=dict(home=.4,draw=.3,away=.3),
                               dynamic=dict(home=.8,draw=.1,away=.1)))
            r=dict(observations=[],observed_at=(t+timedelta(hours=2)).isoformat(),
                   outcome="home" if i<20 else y)
            rows.append((b,r))
        return rows
    def test_frozen_weight_independent_of_test_outcome(self):
        # Unit test of selection logic only; replay validation tested above.
        def execute(y):
            rows=self.mock_pairs(y)
            results={b["event_id"]:r for b,r in rows}
            with patch("ops.research_live_calibration_v8.verify_bundle",return_value=True), patch("ops.research_live_calibration_v8.settle",side_effect=lambda b,*a,**k:results[b["event_id"]]), patch("ops.research_live_calibration_v8.MIN_TRAIN",20), patch("ops.research_live_calibration_v8.MIN_TEST",20):
                return calibrate(rows,model_release="mock",train_start="2026-10-01T00:00:00Z",
                    train_cutoff="2026-10-21T00:00:00Z",test_end="2026-11-10T00:00:00Z",as_of="2026-11-11T00:00:00Z")
        a,b=execute("home"),execute("away")
        self.assertTrue(a["weights_fitted"])
        self.assertEqual(a["frozen_policy"],b["frozen_policy"])
        self.assertNotEqual(a["test_metrics"],b["test_metrics"])
        self.assertFalse(a["model_promotion_allowed"])
    def test_duplicate(self):
        b=bundle();r=settle(b,final(),as_of=FIN)
        with self.assertRaises(ValueError):
            calibrate([(b,r),(b,r)],model_release=RELEASE,train_start="2026-11-27T00:00:00Z",
                train_cutoff="2026-11-28T00:00:00Z",test_end="2026-11-29T00:00:00Z",as_of="2026-11-30T00:00:00Z")
