import unittest
from datetime import date
from ops.historical_dc_replay_20261127 import fit,tau,factor,evaluate,dated_rates,EXTRA
from ops.historical_fair_model_replay_20261127 import TeamCounts
from ops.live_score_challenger_20261127 import score_grid

class DCTests(unittest.TestCase):
    def test_fit_direction(self):
        self.assertEqual(fit([((1,1),(0,0))]*10)[0],-.15)
        self.assertEqual(fit([((1,1),(1,0))]*10)[0],.15)
        self.assertEqual(fit([((1,1),(2,2))]*10)[0],0)
        with self.assertRaises(ValueError): fit([])
    def test_factor_and_mass(self):
        for h in (.2,1,2,3):
            for a in (.2,1,2,3):
                for rho in (-.1,0,.1):
                    t=tau((h,a),rho)
                    g=score_grid((0,0),h,a,rho)
                    b=score_grid((0,0),h,a)
                    self.assertAlmostEqual(sum(g.values()),1)
                    for f in [(0,0),(0,1),(1,0),(1,1),(2,2)]:
                        self.assertAlmostEqual(g[f],b[f]*factor(f,t))
    def test_same_day_barrier(self):
        d=date(2024,1,1)
        x=[(d,"A","B",(5,0)),(d,"A","C",(0,1))]
        y=[(d,"A","B",(0,5)),(d,"A","C",(1,0))]
        self.assertEqual([m for m,_ in dated_rates(x,TeamCounts([1.5,1.2]))],
                         [m for m,_ in dated_rates(y,TeamCounts([1.5,1.2]))])
    def test_calibration_separate(self):
        tr=[(date(2022,1,1),"A","B",(2,1)),(date(2022,1,2),"B","A",(1,1))]
        cal=[(date(2023,1,1),"A","B",(0,0)),(date(2023,1,2),"B","A",(1,1))]
        a=evaluate(tr,cal,[(date(2024,1,1),"A","B",(0,0))])
        b=evaluate(tr,cal,[(date(2024,1,1),"A","B",(4,3))])
        self.assertEqual(a["rho"],b["rho"])
        self.assertEqual(a["cal_delta"],b["cal_delta"])
        self.assertFalse(a["positive_ev_verified"])
        with self.assertRaises(ValueError): evaluate(tr,cal,cal)
    def test_manifest(self):
        self.assertEqual(sum(v[1] for v in EXTRA.values()),612)

if __name__=="__main__": unittest.main()
