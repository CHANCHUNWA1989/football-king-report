import unittest
from copy import deepcopy
from ops.cross_market_coherence import audit, compare_context, _grade


def sample():
    return dict(fixture='synthetic',score=[1,0],reds=[0,1],observed_at='2026-01-01T01:00:00Z',cutoff='2026-01-01T01:01:00Z',generated_at='2026-01-01T01:01:01Z',home_line4=-5,over_line4=9,cells=[[1,0,.2],[2,0,.3],[2,1,.5]])


class CrossMarket(unittest.TestCase):
    def test_distribution(self):
        x=audit(sample()); d=x['derived']
        self.assertEqual(d['1x2']['home'],1)
        self.assertAlmostEqual(d['ah']['half_loss'],.7)
        self.assertAlmostEqual(d['ah']['full_win'],.3)
        self.assertAlmostEqual(d['total']['half_loss'],.3)
        self.assertAlmostEqual(d['total']['full_win'],.5)
        self.assertFalse(x['production_enabled'])
    def test_grade_grid(self):
        for margin in range(-10,11):
            for line in range(-40,41):
                legs=[line-1,line+1] if line%2 else [line,line]
                sign=sum(1 if 4*margin+l>0 else -1 if 4*margin+l<0 else 0 for l in legs)
                self.assertEqual(_grade(4*margin,line),('full_loss','half_loss','push','half_win','full_win')[sign+2])
    def test_declared(self):
        s=sample(); s['declared']=audit(s)['derived']; audit(s)
        s['declared']['1x2']['home']=.9
        self.assertRaises(ValueError,audit,s)
    def test_bad_grid(self):
        for cells in ([[0,0,1]],[[1,0,.5],[1,0,.5]],[[1,0,.9]],[[1,0,float('nan')]],[[1,0,True]]):
            s=sample(); s['cells']=cells; self.assertRaises(ValueError,audit,s)
    def test_cutoff(self):
        s=sample(); s['observed_at']='2026-01-01T02:00:00Z'; self.assertRaises(ValueError,audit,s)
    def test_naive(self):
        s=sample(); s['cutoff']='2026-01-01T01:01:00'; self.assertRaises(ValueError,audit,s)
    def test_context(self):
        a=sample(); b=deepcopy(a); b['cutoff']='2026-01-01T09:01:00+08:00'; self.assertEqual(compare_context(a,b)['state'],'HOLD')
        for k,v in [('reds',[0,0]),('fixture','other'),('score',[0,0]),('home_line4',-6),('over_line4',10),('cutoff','2026-01-01T01:00:59Z')]:
            b=deepcopy(a); b[k]=v; self.assertRaises(ValueError,compare_context,a,b)
