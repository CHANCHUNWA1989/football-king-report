import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_unified_score_fusion import (mix_grid,projection,weighted_projection,
    observations,actual,scores,assess,select,WEIGHTS)
from score_distribution_vnext import score_matrix

class UnifiedScoreFusionTests(unittest.TestCase):
    def test_common_matrix(self):
        grids=[score_matrix(.5+i*.5,1.3-i*.1) for i in range(5)]
        for weights in WEIGHTS.values():
            matrix=mix_grid(grids,weights)
            self.assertAlmostEqual(math.fsum(v for r in matrix for v in r),1.)
            a=projection(matrix)
            b=weighted_projection([projection(g) for g in grids],weights)
            for x,y in zip(a,b):self.assertAlmostEqual(x,y,places=11)
    def test_invalid_weights(self):
        with self.assertRaises(ValueError):
            mix_grid([score_matrix(1,1)]*5,(1,1,0,0,0))
    def test_grade_mass(self):
        p=projection(score_matrix(1.2,.8))
        self.assertAlmostEqual(sum(p[:3]),1.)
        for j in range(4):self.assertAlmostEqual(sum(p[5+j*5:10+j*5]),1.)
        self.assertLessEqual(p[3],p[4])
    def test_quarter_lines(self):
        # Draw: home -0.25 half loss, +0.25 half win.
        self.assertEqual(actual(1,1)[3],(4,3,1,0))
    def test_no_same_date_training(self):
        rows=[("2022-08-01",str(i),"B",1,0) for i in range(51)]
        self.assertEqual(observations(rows),[])
        obs=observations(rows+[("2022-08-02","A","B",1,1)])
        self.assertEqual(len(obs),1)
        self.assertEqual(assess(obs,"equal")["n"],1)
    def test_selection_requires_cohort(self):
        with self.assertRaises(ValueError):select([])
    def test_perfect_scores(self):
        g=((0.,0.),(0.,1.))
        p=projection(g)
        self.assertEqual(scores(p,actual(1,1)),(0.,0.,1,0.,0.,0.,0.))
