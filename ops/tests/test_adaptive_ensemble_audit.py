import unittest
from datetime import datetime, timezone, timedelta
from ops.adaptive_ensemble_audit import evaluate


def rows(n=8):
    out=[]
    for i in range(n):
        t=datetime(2025,1,6,12,tzinfo=timezone.utc)+timedelta(weeks=i)
        out.append(dict(fixture=str(i),cutoff=(t-timedelta(hours=1)).isoformat(),kickoff=t.isoformat(),settled_at=(t+timedelta(hours=2)).isoformat(),outcome=0,forecasts={'baseline':[.4,.3,.3],'better':[.8,.1,.1],'worse':[.1,.4,.5]}))
    return out


class TestEnsemble(unittest.TestCase):
    def ev(self,r): return evaluate(r,['better','worse'],minimum=2)
    def test_weights(self):
        a=self.ev(rows()); self.assertEqual(a['weekly'][0]['weights']['baseline'],1)
        for w in a['weekly']:
            self.assertAlmostEqual(sum(w['weights'].values()),1); self.assertGreaterEqual(w['weights']['baseline'],.5)
        self.assertGreater(a['log_loss_delta'],0); self.assertEqual(a['certified_cases'],0)
    def test_future(self):
        r=rows(); a=self.ev(r); r[-1]['outcome']=2; self.assertEqual(a['predictions'],self.ev(r)['predictions'])
    def test_late(self):
        r=rows(); r[0]['settled_at']='2026-01-01T00:00:00Z'; self.assertEqual(self.ev(r)['weekly'][2]['weights']['baseline'],1)
    def test_order(self): self.assertEqual(self.ev(rows()),self.ev(rows()[::-1]))
    def test_duplicate(self):
        r=rows(); self.assertRaises(ValueError,self.ev,r+[r[0]])
    def test_bad(self):
        r=rows(); r[0]['forecasts']['better']=[float('nan'),0,1]; self.assertRaises(ValueError,self.ev,r)
    def test_missing(self):
        r=rows(); del r[0]['forecasts']['better']; self.assertRaises(ValueError,self.ev,r)
    def test_empty(self): self.assertIsNone(self.ev([])['log_loss_delta'])
    def test_anchor(self): self.assertEqual(evaluate(rows(),['better','worse'],minimum=1,anchor=1)['log_loss_delta'],0)
    def test_boundary(self):
        r=rows(); r[0]['settled_at']='2025-01-13T00:00:00Z'; self.assertEqual(evaluate(r,['better','worse'],minimum=1)['weekly'][1]['prior_settled'],0)
