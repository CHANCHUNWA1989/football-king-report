import unittest
from datetime import date,timedelta
from types import SimpleNamespace
from ops.common_grid_historical_replay import (
    rates_grid, fitted_grid, checked_grid, evaluate, projections, mix, MODELS,
)
from ops.dynamic_2026_date_split_audit import evaluate as historical
from ops.tests.test_bivariate_real_2026_paired_oos import rows, FakeModel


class WideFake(FakeModel):
    def predict(self,home,away,*,max_goals=15,normalize=True):
        g=[[0.]*max_goals for _ in range(max_goals)]
        g[0][0],g[1][0],g[0][1],g[2][1]=.2,.3,.2,.3
        return SimpleNamespace(grid=g,home_draw_away=(.6,.2,.2))


class CommonGridReplayTests(unittest.TestCase):
    def test_grid_and_market_projection(self):
        g,t=rates_grid(1.7,1.1)
        self.assertLess(t,1e-7)
        p=projections(g)
        self.assertAlmostEqual(sum(p["1X2"].values()),1.)
        self.assertAlmostEqual(p["AH_HOME_-1.25"]["HALF_LOSS"],
                               sum(g[i][i-1] for i in range(1,25)))
        self.assertAlmostEqual(p["OVER_2.75"]["HALF_WIN"],sum(g[i][3-i] for i in range(4)))

    def test_degenerate_mixture_and_invalid_mass(self):
        g=rates_grid(1.7,1.1)[0]
        x=mix({m:g for m in MODELS},{m:.25 for m in MODELS})
        self.assertAlmostEqual(x[0][0],g[0][0])
        with self.assertRaises(ValueError):
            checked_grid([[0.]*25 for _ in range(25)])

    def test_wide_grid_check(self):
        m=WideFake([],[],[],[])
        g,t=fitted_grid(m,"h","a")
        self.assertEqual(t,0.)
        self.assertAlmostEqual(g[0][0],.2)
        class Bad(WideFake):
            def predict(self,*args,**kwargs):
                result=super().predict(*args,**kwargs)
                if kwargs["max_goals"]==35:
                    result.grid[0][0]-=.01
                    result.grid[30][30]=.01
                return result
        with self.assertRaises(ValueError):
            fitted_grid(Bad([],[],[],[]),"h","a")

    def test_same_cohort_and_gate(self):
        days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(35)]
        g={m:rates_grid(1.1+i*.2,.9)[0] for i,m in enumerate(MODELS)}
        out=evaluate(days,[[1,0]]*35,[g]*35)
        self.assertEqual(out["paired_n"],35)
        self.assertEqual(out["adaptive_active_n"],4)
        for metrics in out["all_cohort"].values():
            self.assertEqual(len(metrics),9)
            self.assertTrue(all(x["n"]==35 for x in metrics.values()))
        self.assertEqual(out["status"],"HOLD")
        self.assertFalse(out["model_promoted"])

    def test_existing_replay_opt_in(self):
        train,test=rows()
        pkg=SimpleNamespace(PoissonGoalsModel=WideFake,DixonColesGoalModel=WideFake)
        out=historical(train,test,model_module=pkg,min_train=30,min_test=5,common_grid=True)
        self.assertEqual(out["common_grid_replay"]["paired_n"],8)
        self.assertIsNone(out["common_grid_replay"]["active_cohort"])
        self.assertEqual(out["same_eligible_heldout_games"],8)


if __name__=="__main__":
    unittest.main()
