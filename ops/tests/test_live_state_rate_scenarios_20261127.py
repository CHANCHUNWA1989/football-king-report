import unittest
from math import exp
from ops.live_state_rate_scenarios_20261127 import remaining_rates,scenario,sensitivity

NEUTRAL=dict(own_red_log=0,opponent_red_log=0,trailing_log=0,leading_log=0)
CARD=dict(own_red_log=-.3,opponent_red_log=.2,trailing_log=.15,leading_log=-.1)

class RateTests(unittest.TestCase):
    def test_neutral_and_time(self):
        self.assertEqual(remaining_rates((0,0),(0,0),2700,(2,1),**NEUTRAL),(1,.5))
        self.assertEqual(remaining_rates((1,0),(1,0),0,(2,1),**CARD),(0,0))
        s=scenario((0,1),(1,0),0,(2,1),**CARD)
        self.assertEqual(s["one_x_two"],(0,0,1))
        self.assertEqual(s["trailing_side_final_win"],0)
        self.assertEqual(s["trailing_side_avoid_defeat"],0)
    def test_dismissal_direction(self):
        h,a=remaining_rates((0,0),(1,0),5400,(2,1),**CARD)
        self.assertAlmostEqual(h,2*exp(-.3))
        self.assertAlmostEqual(a,exp(.2))
        self.assertLess(h,2)
        self.assertGreater(a,1)
    def test_trailing_direction(self):
        s=scenario((0,1),(0,0),1800,(1.5,1.5),**CARD)
        self.assertEqual(s["trailing_side"],"home")
        self.assertAlmostEqual(s["trailing_side_final_win"],s["one_x_two"][0])
        self.assertAlmostEqual(s["trailing_side_avoid_defeat"],sum(s["one_x_two"][:2]))
        self.assertIsNone(scenario((1,1),(0,0),1800,(1,1),**CARD)["trailing_side"])
    def test_grid(self):
        # 5 scores x 4 red states x 4 horizons x 3 baseline pairs x 2 coefficient sets
        for score in [(0,0),(1,0),(0,1),(2,0),(0,2)]:
            for cards in [(0,0),(1,0),(0,1),(1,1)]:
                for seconds in (0,600,2700,5400):
                    for rates in [(1,1),(2,.7),(.7,2)]:
                        for coeff in (NEUTRAL,CARD):
                            s=scenario(score,cards,seconds,rates,**coeff)
                            t=scenario(score[::-1],cards[::-1],seconds,rates[::-1],**coeff)
                            self.assertAlmostEqual(sum(s["one_x_two"]),1)
                            self.assertAlmostEqual(s["expected_final_goals"],sum(score)+sum(s["remaining_goal_means"]),places=10)
                            for x,y in zip(s["one_x_two"],t["one_x_two"][::-1]):
                                self.assertAlmostEqual(x,y)
                            self.assertFalse(s["qualified"])
                            self.assertFalse(s["live_xg_verified"])
    def test_range(self):
        s=sensitivity((0,0),(1,0),2700,(1,1),[NEUTRAL,CARD])
        self.assertEqual(s["scenario_count"],2)
        self.assertFalse(s["range_is_confidence_interval"])
        self.assertTrue(all(0<=lo<=hi<=1 for lo,hi in s["one_x_two_ranges"]))
    def test_invalid(self):
        for args in [((0,0),(5,0),100,(1,1)),((0,0),(True,0),100,(1,1)),
                     ((0,0),(0,0),-1,(1,1)),((0,0),(0,0),100,(float("nan"),1))]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                remaining_rates(*args,**CARD)
        with self.assertRaises(ValueError):
            remaining_rates((0,0),(0,0),100,(1,1),**dict(CARD,own_red_log=.2))

if __name__=="__main__": unittest.main()
