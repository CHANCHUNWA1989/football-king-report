import unittest
from math import fsum
from ops.live_score_transition_20261127 import transition_grid,transition_scenario
from ops.live_score_challenger_20261127 import score_grid
from ops.live_state_rate_scenarios_20261127 import scenario

NEUTRAL=dict(own_red_log=0,opponent_red_log=0,trailing_log=0,leading_log=0)
TACTICAL=dict(own_red_log=-.3,opponent_red_log=.2,trailing_log=.4,leading_log=-.3)

class TransitionTests(unittest.TestCase):
    def test_neutral_exact_reference(self):
        for score in [(0,0),(1,0),(0,2)]:
            for rates in [(0,0),(1,1),(2,.7),(.7,2)]:
                for seconds in (0,900,5400):
                    g,b,k=transition_grid(score,(0,0),seconds,rates,**NEUTRAL)
                    ref=score_grid(score,*(x*seconds/5400 for x in rates))
                    self.assertLess(fsum(abs(g.get(s,0)-ref.get(s,0))
                                           for s in g.keys()|ref.keys()),3e-12)
                    self.assertLessEqual(b,1e-12)
    def test_state_change(self):
        s=transition_scenario((0,0),(0,0),5400,(1.5,1.5),**TACTICAL)
        fixed=scenario((0,0),(0,0),5400,(1.5,1.5),**TACTICAL)
        self.assertGreater(s["one_x_two"][1],fixed["one_x_two"][1])
        self.assertFalse(s["qualified"])
        self.assertFalse(s["future_cards_simulated"])
    def test_stress(self):
        # 5 scores x 4 card states x 3 horizons x 3 rate pairs x 2 coefficient sets.
        for score in [(0,0),(1,0),(0,1),(2,0),(0,2)]:
            for cards in [(0,0),(1,0),(0,1),(1,1)]:
                for seconds in (0,900,5400):
                    for rates in [(1,1),(2,.7),(.7,2)]:
                        for coeff in (NEUTRAL,TACTICAL):
                            s=transition_scenario(score,cards,seconds,rates,**coeff)
                            t=transition_scenario(score[::-1],cards[::-1],seconds,rates[::-1],**coeff)
                            self.assertAlmostEqual(sum(s["one_x_two"]),1,places=12)
                            self.assertLessEqual(s["poisson_tail_upper_bound"],1e-12)
                            self.assertTrue(all(0<=p<=1+1e-12 for p in s["one_x_two"]))
                            for x,y in zip(s["one_x_two"],t["one_x_two"][::-1]):
                                self.assertAlmostEqual(x,y,places=12)
                            self.assertFalse(s["qualified"])
    def test_high_rate_tail(self):
        g,b,k=transition_grid((0,0),(0,0),5400,(6,6),**NEUTRAL)
        self.assertLessEqual(b,1e-12)
        self.assertAlmostEqual(fsum(g.values()),1,places=12)
        self.assertLessEqual(k,100)
    def test_bad_inputs(self):
        for args in [((0,0),(5,0),100,(1,1)),((0,0),(0,0),-1,(1,1)),
                     ((True,0),(0,0),100,(1,1)),((0,0),(0,0),100,(float("nan"),1))]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                transition_grid(*args,**TACTICAL)

if __name__=="__main__": unittest.main()
