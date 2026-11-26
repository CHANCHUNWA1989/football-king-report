import unittest
from datetime import datetime, timedelta, timezone
from ops.deep_grade_uncertainty import compare


def rows(n=60):
    return [dict(fixture=str(i),league='A' if i%2 else 'B',kickoff=(datetime(2025,1,6,tzinfo=timezone.utc)+timedelta(weeks=i//5)).isoformat(),grade='push',baseline=[.2]*5,challenger=[.1,.1,.6,.1,.1]) for i in range(n)]

class TestDeepGradeUncertainty(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(compare([])['brier_delta'])
    def test_underpowered(self):
        self.assertIsNone(compare(rows(59))['brier_ci'])
    def test_positive_reproducible(self):
        a=compare(rows()); self.assertEqual(a,compare(rows()))
        self.assertGreater(a['brier_ci'][0],0); self.assertGreater(a['log_loss_ci'][0],0)
        self.assertFalse(a['production_enabled']); self.assertEqual(a['certified_cases'],0)
    def test_identical(self):
        r=rows(); [x.update(challenger=x['baseline']) for x in r]
        self.assertEqual(compare(r)['log_loss_ci'],[0,0])
    def test_duplicate(self):
        r=rows(); self.assertRaises(ValueError,compare,r+[r[0]])
    def test_bad_probs(self):
        for p in ([.1]*5,[float('nan'),0,0,0,1],[True,0,0,0,0]):
            r=rows(1); r[0]['baseline']=p; self.assertRaises(ValueError,compare,r)
    def test_utc_boundary(self):
        r=rows(2); r[0]['kickoff']='2025-01-05T23:30:00Z'; r[1]['kickoff']='2025-01-06T00:30:00+01:00'
        self.assertEqual(compare(r)['weeks'],1)
    def test_naive(self):
        r=rows(1); r[0]['kickoff']='2025-01-06T00:00:00'; self.assertRaises(ValueError,compare,r)
    def test_reversed(self):
        r=rows(); [x.update(baseline=x['challenger'],challenger=x['baseline']) for x in r]
        self.assertLess(compare(r)['brier_ci'][1],0)
