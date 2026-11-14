"""Synthetic offline evaluation tests. Not evidence of betting profitability."""
import unittest
from ops.backtest_evaluation import evaluate_binary, evaluate_settled_returns, PRODUCTION_RECOMMENDATIONS

def r(i, p, y, capture="2026-01-01T10:00:00+00:00"):
    return {"event_id":str(i),"captured_at":capture,
            "kickoff_at":f"2026-01-0{i}T12:00:00+00:00",
            "probability":p,"outcome":y}

class BacktestTests(unittest.TestCase):
    def test_perfect_holdout(self):
        result = evaluate_binary([r(1,.5,0),r(2,1,1),r(3,0,0)],min_train=1)
        self.assertEqual(result["brier"],0)
        self.assertEqual(result["holdout_count"],2)
        self.assertFalse(result["out_of_sample_verified"])
    def test_miscalibrated(self):
        self.assertAlmostEqual(evaluate_binary([r(1,.5,1),r(2,.9,0)],min_train=1)["brier"],.81)
    def test_duplicate_ids(self):
        with self.assertRaises(ValueError): evaluate_binary([r(1,.5,0),r(1,.5,1)])
    def test_future_capture(self):
        with self.assertRaises(ValueError): evaluate_binary([r(1,.5,0),r(2,.5,1,"2026-01-02T13:00:00+00:00")])
    def test_naive_timestamp(self):
        with self.assertRaises(ValueError): evaluate_binary([r(1,.5,0),r(2,.5,1,"2026-01-01T10:00:00")])
    def test_invalid_probability(self):
        with self.assertRaises(ValueError): evaluate_binary([r(1,.5,0),r(2,1.1,1)])
    def test_same_boundary_time(self):
        x=r(2,.5,1);x["kickoff_at"]="2026-01-01T12:00:00+00:00"
        with self.assertRaises(ValueError): evaluate_binary([r(1,.5,0),x])
    def test_returns(self):
        rows=[{"market":"total","side":"under","line":2.5,"home_goals":0,"away_goals":0,"odds":1.87,"stake":10},
              {"market":"handicap","side":"home","line":-1,"home_goals":0,"away_goals":1,"odds":4.2,"stake":10}]
        x=evaluate_settled_returns(rows)
        self.assertEqual(str(x["net"]),"-1.30")
        self.assertEqual(str(x["roi"]),"-0.065")
        self.assertFalse(x["positive_ev_verified"])
    def test_bad_stake(self):
        with self.assertRaises(ValueError):
            evaluate_settled_returns([{"stake":0}])
    def test_hold(self):
        self.assertEqual(PRODUCTION_RECOMMENDATIONS,"DISABLED")

if __name__=="__main__":
    unittest.main()
