import unittest
from ou25_independent_backtest import audit

class BacktestTests(unittest.TestCase):
    def test_sealed_prediction_settles(self):
        predictions=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
                      "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}]
        results=[{"fixture_id":"a","status":"FT","home_goals":2,"away_goals":1}]
        report=audit(predictions,results)
        self.assertEqual(report["settled_count"],1)
        self.assertEqual(report["mean_brier"],0.16)
        self.assertEqual(report["calibration_status"],"INSUFFICIENT_EVIDENCE")
    def test_post_kickoff_predictions_rejected(self):
        p=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T13:00:00Z",
            "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.9}]
        r=[{"fixture_id":"a","status":"FT","home_goals":4,"away_goals":0}]
        self.assertEqual(audit(p,r)["settled_count"],0)
    def test_duplicate_prediction_rejected(self):
        p={"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
           "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}
        r=[{"fixture_id":"a","status":"FT","home_goals":2,"away_goals":1}]
        report=audit([p,p],r)
        self.assertEqual(report["settled_count"],1)
        self.assertEqual(report["rejected_count"],1)

if __name__=="__main__":
    unittest.main()
