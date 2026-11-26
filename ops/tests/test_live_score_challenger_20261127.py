import unittest
from math import fsum
from ops.live_score_challenger_20261127 import score_grid, summarize, paired_evaluate

def example(**kw):
    r=dict(fixture_id="fixture-1",decision_at="2026-11-26T14:47:00Z",
           settled_at="2026-11-26T16:00:00Z",baseline=[.3,.4,.3],
           challenger=[.2,.6,.2],outcome=1)
    for m in ("baseline","challenger"):
        r[m+"_trained_through"]="2026-11-25T00:00:00Z"
        r[m+"_features_through"]="2026-11-26T14:46:00Z"
        r[m+"_issued_at"]="2026-11-26T14:46:30Z"
    r.update(kw)
    return r

class ScoreTests(unittest.TestCase):
    def test_mass_and_symmetry(self):
        # 4 current states x 5 home means x 5 away means x 3 correlations
        for score in [(0,0),(1,0),(0,1),(2,2)]:
            for h in (0,.25,.5,1,2):
                for a in (0,.25,.5,1,2):
                    for rho in (-.1,0,.1):
                        g=score_grid(score,h,a,rho)
                        self.assertAlmostEqual(fsum(g.values()),1,places=12)
                        self.assertGreaterEqual(min(g.values()),0)
                        s=summarize(g)
                        self.assertAlmostEqual(sum(s["one_x_two"]),1)
                        self.assertLessEqual(s["total_at_most_one"],s["total_at_most_two"])
                        self.assertFalse(s["fitted"])
                        t=summarize(score_grid(score[::-1],a,h,rho))
                        for p,q in zip(s["one_x_two"],t["one_x_two"][::-1]):
                            self.assertAlmostEqual(p,q)
    def test_zero_remaining(self):
        self.assertEqual(summarize(score_grid((0,1),0,0))["one_x_two"],(0,0,1))
    def test_dc_low_score(self):
        p=score_grid((0,0),1,1,0)
        q=score_grid((0,0),1,1,-.1)
        self.assertGreater(q[0,0],p[0,0])
        self.assertGreater(q[1,1],p[1,1])
        self.assertLess(q[0,1],p[0,1])
        self.assertEqual(q[2,2],p[2,2])
    def test_bad_inputs(self):
        for args in [((0,0),-1,1,0),((True,0),1,1,0),((0,0),12,12,.5),
                     ((0,0),float("nan"),1,0),((0,0),1,1,True)]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                score_grid(*args)
    def test_paired(self):
        r=paired_evaluate([example()])
        self.assertTrue(all(x<0 for x in r["mean_challenger_minus_baseline"].values()))
        self.assertFalse(r["out_of_sample_verified"])
        self.assertFalse(r["confidence_interval_verified"])
    def test_leakage(self):
        for patch in [
            {"baseline_trained_through":"2026-11-26T14:47:00Z"},
            {"challenger_issued_at":"2026-11-26T14:48:00Z"},
            {"baseline_features_through":"2026-11-26T14:46:45Z"},
            {"settled_at":"2026-11-26T14:47:00Z"},
            {"outcome":True},{"baseline":[.5,.5,.5]},
            {"decision_at":"2026-11-26T14:47:00"}]:
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                paired_evaluate([example(**patch)])
        with self.assertRaises(ValueError):
            paired_evaluate([example(),example()])

if __name__=="__main__": unittest.main()
