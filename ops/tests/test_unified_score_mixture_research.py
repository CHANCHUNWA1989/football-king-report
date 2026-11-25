"""Synthetic common-PMF mixture tests, not predictive validation."""
import math
import unittest
from ops.unified_score_mixture_research import (
    analyze, mix_scenarios, MODELS, AH_LINES, TOTAL_LINES, OPPOSITE,
)
from ops.core_unified_score_grid import score_grid, RHO, GRADES


class UnifiedScoreMixtureTests(unittest.TestCase):
    def setUp(self):
        self.rates=dict(zip(MODELS,((1.2,.8),(2.1,1.1))))
        self.weights=dict(zip(MODELS,(.35,.65)))

    def test_convex_cell_oracle_and_mass(self):
        g,t=mix_scenarios(self.rates,self.weights)
        a,_=score_grid(*self.rates[MODELS[0]],rho=0.)
        b,_=score_grid(*self.rates[MODELS[1]],rho=RHO)
        for i in range(25):
            for j in range(25):
                self.assertAlmostEqual(g[i][j],.35*a[i][j]+.65*b[i][j],places=14)
        self.assertAlmostEqual(math.fsum(math.fsum(row) for row in g),1.,places=12)
        self.assertGreaterEqual(t,0.)

    def test_degenerate_weights_recover_component(self):
        for m,rho in zip(MODELS,(0.,RHO)):
            g,_=mix_scenarios(self.rates,{k:float(k==m) for k in MODELS})
            single,_=score_grid(*self.rates[m],rho=rho)
            self.assertEqual(g,single)

    def test_all_markets_and_deep_lines(self):
        out=analyze(self.rates,self.weights)
        g=out["score_matrix"]
        self.assertEqual(len(out["asian_handicap"]),17)
        self.assertEqual(len(out["total_goals"]),9)
        for line in AH_LINES:
            h=out["asian_handicap"][str(line)]["home"]
            a=out["asian_handicap"][str(line)]["away_opposite_line"]
            self.assertAlmostEqual(sum(h.values()),1.,places=12)
            for k in GRADES:
                self.assertAlmostEqual(h[k],a[OPPOSITE[k]],places=12)
        for line in TOTAL_LINES:
            o=out["total_goals"][str(line)]["over"]
            u=out["total_goals"][str(line)]["under"]
            self.assertAlmostEqual(sum(o.values()),1.,places=12)
            for k in GRADES:
                self.assertAlmostEqual(o[k],u[OPPOSITE[k]],places=12)
        self.assertAlmostEqual(out["asian_handicap"]["-1.25"]["home"]["HALF_LOSS"],
                               sum(g[h][a] for h in range(25) for a in range(25) if h-a==1),places=12)
        self.assertAlmostEqual(out["total_goals"]["2.75"]["over"]["HALF_WIN"],
                               sum(g[h][3-h] for h in range(4)),places=12)

    def test_three_way_draw_is_distinct_from_asian_push(self):
        r=analyze(self.rates,self.weights)
        self.assertAlmostEqual(r["three_way_handicap"]["-1"]["DRAW"],
                               r["asian_handicap"]["-1.0"]["home"]["PUSH"],places=12)
        self.assertNotIn("PUSH",r["three_way_handicap"]["-1"])
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["fitted_historical_models_used"])
        self.assertFalse(r["production_weights_changed"])
        self.assertEqual(r["certified_prospective_samples"],0)

    def test_invalid_input(self):
        for w in ({},dict(zip(MODELS,(.3,.3))),dict(zip(MODELS,(True,0.))),
                  dict(zip(MODELS,(float("nan"),.5))),dict(zip(MODELS,(-.1,1.1)))):
            with self.assertRaises(ValueError):
                mix_scenarios(self.rates,w)
        for pair in ((6.,1.),(.1,float("inf")),(True,1.),(1.,)):
            with self.assertRaises(ValueError):
                mix_scenarios({**self.rates,MODELS[0]:pair},self.weights)

    def test_extreme_rates(self):
        for rates in ((.1,.1),(.1,5.5),(5.5,.1),(5.5,5.5)):
            r=analyze({m:rates for m in MODELS},self.weights)
            self.assertAlmostEqual(sum(r["full_time_1x2"].values()),1.,places=12)
            self.assertLess(r["weighted_unmodeled_tail_bound"],1e-7)


if __name__=="__main__":
    unittest.main()
