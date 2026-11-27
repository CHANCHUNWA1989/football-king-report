import math
import unittest
from ops.research_gas_v1 import State, forecast, update

class ResearchGASTests(unittest.TestCase):
    def test_baseline_and_normalization(self):
        p=forecast(State())
        self.assertAlmostEqual(p["lambda_home"],1.4)
        self.assertAlmostEqual(sum(p["probabilities"].values()),1)
    def test_goals_update(self):
        old=State()
        new=update(old,3,0)
        self.assertGreater(new.home_attack,old.home_attack)
        self.assertLess(new.away_defence,old.away_defence)
    def test_no_future_result_in_forecast(self):
        self.assertEqual(forecast(State()),forecast(State()))
    def test_invalid_values(self):
        for bad in (-1,1.5,True,21):
            with self.assertRaises(ValueError): update(State(),bad,0)
        with self.assertRaises(ValueError): forecast(State(home_attack=float("nan")))
        with self.assertRaises(ValueError): update(State(),1,0,step=float("inf"))
    def test_bounded(self):
        s=State()
        for _ in range(100):
            s=update(s,20,0)
        self.assertTrue(all(math.isfinite(v) and abs(v)<=1.5 for v in vars(s).values()))

if __name__=="__main__": unittest.main()
