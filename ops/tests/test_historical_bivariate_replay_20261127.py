import unittest
from datetime import date
from math import fsum
from ops.historical_bivariate_replay_20261127 import components,exact_probability,probabilities,fit,replay
from ops.live_score_challenger_20261127 import score_grid

class BivariateTests(unittest.TestCase):
    def test_independent_reference(self):
        for mu in ((.2,1),(1,1),(2,.7),(3,2)):
            parts=components(mu,1,0)
            grid=score_grid((0,0),*mu)
            p,t,d=probabilities(parts)
            for k,v in enumerate(p):
                self.assertAlmostEqual(v,fsum(x for (h,a),x in grid.items() if (0 if h>a else 1 if h==a else 2)==k))
            self.assertAlmostEqual(t,fsum(x for (h,a),x in grid.items() if h+a>=5))
            self.assertAlmostEqual(d,fsum(x for (h,a),x in grid.items() if h-a>=2))
    def test_shared_mean_and_symmetry(self):
        for mu in ((.2,1),(1,1),(2,.7),(3,2)):
            for share in (0,.05,.2):
                parts=components(mu,1,share)
                means=[fsum(i*v for i,v in enumerate(p)) for p in parts]
                self.assertAlmostEqual(means[0]+means[2],mu[0])
                self.assertAlmostEqual(means[1]+means[2],mu[1])
                p,t,_=probabilities(parts)
                q,u,_=probabilities(components(mu[::-1],1,share))
                self.assertAlmostEqual(fsum(p),1)
                self.assertAlmostEqual(t,u)
                for x,y in zip(p,q[::-1]): self.assertAlmostEqual(x,y)
                self.assertAlmostEqual(exact_probability(parts,(0,0)),parts[0][0]*parts[1][0]*parts[2][0])
    def test_exact_joint_mass(self):
        parts=components((1,2),1,.2)
        grid={(i,j):exact_probability(parts,(i,j)) for i in range(31) for j in range(31)}
        self.assertAlmostEqual(fsum(grid.values()),1)
        p,t,d=probabilities(parts)
        self.assertAlmostEqual(t,fsum(x for (i,j),x in grid.items() if i+j>=5))
        self.assertAlmostEqual(d,fsum(x for (i,j),x in grid.items() if i-j>=2))
    def test_cutoff(self):
        tr=[(date(2022,1,1),"A","B",(2,1)),(date(2022,1,2),"B","A",(1,1))]
        cal=[(date(2023,1,1),"A","B",(0,0))]
        a=replay(tr,cal,[(date(2024,1,1),"A","B",(0,0))])
        b=replay(tr,cal,[(date(2024,1,1),"A","B",(5,3))])
        self.assertEqual(a["params"],b["params"])
        self.assertFalse(a["positive_ev_verified"])
        with self.assertRaises(ValueError): replay(tr,cal,cal)
    def test_invalid(self):
        with self.assertRaises(ValueError): components((1,1),1,-.1)
        with self.assertRaises(ValueError): fit([], (1,), (0,))

if __name__=="__main__": unittest.main()
