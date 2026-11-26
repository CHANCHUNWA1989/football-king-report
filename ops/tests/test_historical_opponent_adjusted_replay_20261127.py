import unittest
from datetime import date
from math import fsum
from ops.historical_opponent_adjusted_replay_20261127 import fit,replay,measures,MANIFEST

class OpponentAdjustedTests(unittest.TestCase):
    def test_neutral(self):
        a,d,it=fit({("A","B"):(10,[20,10]),("B","A"):(10,[20,10])},2,0)
        self.assertEqual(a,{"A":1,"B":1})
        self.assertEqual(d,{"B":1,"A":1})
        self.assertEqual(it,1)
    def test_stationarity(self):
        edges={("A","B"):(4,[12,3]),("A","C"):(3,[1,4]),("B","C"):(4,[5,5])}
        a,d,it=fit(edges,1.5,0)
        for team,v in a.items():
            num=15+fsum(g[0] for (h,_),(n,g) in edges.items() if h==team)
            den=15+1.5*fsum(n*d[k] for (h,k),(n,g) in edges.items() if h==team)
            self.assertAlmostEqual(v,num/den,places=8)
        for team,v in d.items():
            num=15+fsum(g[0] for (_,k),(n,g) in edges.items() if k==team)
            den=15+1.5*fsum(n*a[h] for (h,k),(n,g) in edges.items() if k==team)
            self.assertAlmostEqual(v,num/den,places=8)
        self.assertLessEqual(it,150)
    def test_same_day_barrier(self):
        tr=[(date(2020,1,1),"A","B",(2,1)),(date(2020,1,2),"B","A",(1,1))]
        d=date(2021,1,1)
        a=replay(tr,[(d,"A","B",(4,0)),(d,"B","A",(0,1))])
        b=replay(tr,[(d,"B","A",(0,1)),(d,"A","B",(4,0))])
        self.assertEqual(a["correct"],b["correct"])
        for x,y in zip(a["metrics"],b["metrics"]):
            for m in x:self.assertAlmostEqual(x[m],y[m])
        self.assertFalse(a["positive_ev_verified"])
        with self.assertRaises(ValueError): replay(tr,tr)
    def test_measures(self):
        v,correct=measures((0,0),(0,0))
        self.assertEqual(v,(0,0,0,0,0,0))
        self.assertEqual(correct,1)
    def test_manifest(self):
        self.assertEqual(sum(v[1] for v in MANIFEST.values()),1678)
        with self.assertRaises(ValueError): fit({},0,0)

if __name__=="__main__": unittest.main()
