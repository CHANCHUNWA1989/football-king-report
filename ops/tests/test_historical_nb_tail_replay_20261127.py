import unittest
from datetime import date
from math import fsum
from ops.historical_nb_tail_replay_20261127 import pmf,fit,replay,ALPHAS
from ops.live_score_challenger_20261127 import poisson

class NegativeBinomialTests(unittest.TestCase):
    def test_mass_mean_variance(self):
        for mu in (0,.2,1,2,4,8,12):
            for a in ALPHAS:
                p=pmf(mu,a)
                self.assertAlmostEqual(fsum(p),1,places=12)
                self.assertAlmostEqual(fsum(i*v for i,v in enumerate(p)),mu,places=8)
                self.assertAlmostEqual(fsum((i-mu)**2*v for i,v in enumerate(p)),mu+a*mu*mu,places=7)
                self.assertTrue(all(v>=0 for v in p))
    def test_poisson_limit(self):
        for mu in (0,.2,1,4,12):
            p=pmf(mu,0);q=poisson(mu)
            self.assertLess(fsum(abs((p[i] if i<len(p) else 0)-(q[i] if i<len(q) else 0))
                                 for i in range(max(len(p),len(q)))),2e-12)
    def test_fit_direction(self):
        self.assertEqual(fit([((1,1),(1,1))]*10)[0],0)
        self.assertGreater(fit([((1,1),(0,0)),((1,1),(5,5))]*10)[0],0)
        with self.assertRaises(ValueError): fit([])
    def test_cutoff(self):
        tr=[(date(2022,1,1),"A","B",(2,1)),(date(2022,1,2),"B","A",(1,1))]
        cal=[(date(2023,1,1),"A","B",(0,0))]
        a=replay(tr,cal,[(date(2024,1,1),"A","B",(0,0))])
        b=replay(tr,cal,[(date(2024,1,1),"A","B",(5,3))])
        self.assertEqual(a["alpha"],b["alpha"])
        self.assertEqual(a["calibration_scores"],b["calibration_scores"])
        self.assertFalse(a["positive_ev_verified"])
        with self.assertRaises(ValueError): replay(tr,cal,cal)
    def test_invalid(self):
        for mu,a in [(-1,0),(13,0),(float("nan"),0),(1,-.1),(1,1)]:
            with self.assertRaises(ValueError): pmf(mu,a)

if __name__=="__main__": unittest.main()
