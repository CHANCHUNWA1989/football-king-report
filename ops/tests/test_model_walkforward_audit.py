import unittest
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from ops.model_walkforward_audit import evaluate


def rows(n=8):
    out=[]
    for i in range(n):
        t=datetime(2026,1,5,12,tzinfo=timezone.utc)+timedelta(weeks=i)
        out.append(dict(fixture=str(i),kickoff=t.isoformat(),cutoff=(t-timedelta(hours=1)).isoformat(),settled_at=(t+timedelta(hours=2)).isoformat(),outcome=0,forecasts={'baseline':[.4,.3,.3],'better':[.8,.1,.1],'worse':[.1,.4,.5]}))
    return out


class TestAudit(unittest.TestCase):
    def run_rows(self,r): return evaluate(r,['better','worse'],minimum=2)
    def test_selection(self):
        a=self.run_rows(rows()); self.assertEqual(a['selection_counts'],{'baseline':2,'better':6,'worse':0}); self.assertGreater(a['log_loss_delta'],0); self.assertFalse(a['production_enabled']); self.assertEqual(a['certified_cases'],0)
    def test_late_results(self):
        r=rows(); r[0]['settled_at']='2026-03-05T00:00:00Z'; self.assertEqual(self.run_rows(r)['weekly'][2]['model'],'baseline')
    def test_future_mutation(self):
        r=rows(); a=self.run_rows(r); r[-1]['outcome']=2; self.assertEqual(a['weekly'],self.run_rows(r)['weekly'])
    def test_order(self): self.assertEqual(self.run_rows(rows()),self.run_rows(rows()[::-1]))
    def test_duplicate(self):
        r=rows(); self.assertRaises(ValueError,self.run_rows,r+[r[0]])
    def test_missing(self):
        r=rows(); del r[0]['forecasts']['worse']; self.assertRaises(ValueError,self.run_rows,r)
    def test_invalid_prob(self):
        r=rows(); r[0]['forecasts']['better']=[float('nan'),0,1]; self.assertRaises(ValueError,self.run_rows,r)
    def test_time(self):
        r=rows(); r[0]['cutoff']=r[0]['kickoff']; self.assertRaises(ValueError,self.run_rows,r)
    def test_empty(self): self.assertIsNone(self.run_rows([])['log_loss_delta'])
    def test_same_week(self):
        r=rows(2); r[1].update(kickoff='2026-01-06T12:00:00Z',cutoff='2026-01-06T11:00:00Z',settled_at='2026-01-06T14:00:00Z'); self.assertEqual(evaluate(r,['better','worse'],minimum=1)['selection_counts']['baseline'],2)
