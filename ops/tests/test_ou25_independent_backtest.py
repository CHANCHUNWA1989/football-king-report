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
    def test_no_hindsight_baseline_from_heldout_results(self):
        p=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
            "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}]
        r=[{"fixture_id":"a","status":"FT","home_goals":2,"away_goals":1}]
        output=audit(p,r)
        self.assertIsNone(output["constant_rate_baseline_brier"])
        self.assertIsNone(output["outperforms_constant_rate_baseline"])
        self.assertEqual(output["baseline_evidence_status"],"MISSING_TRAINING_BASELINE")
        self.assertEqual(output["production_recommendations"],"DISABLED")

    def test_train_only_pre_forecast_baseline_scored_without_leakage(self):
        p=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
            "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}]
        r=[{"fixture_id":"a","status":"FT","home_goals":2,"away_goals":1}]
        prior={"probability_over":0.3,"sample_count":200,
               "training_cutoff_utc":"2026-10-14T23:59:59Z","source":"prior-season-fixed"}
        output=audit(p,r,baseline=prior)
        self.assertEqual(output["mean_brier"],0.16)
        self.assertEqual(output["constant_rate_baseline_brier"],0.49)
        self.assertTrue(output["outperforms_constant_rate_baseline"])
        self.assertFalse(output["training_baseline_independently_authenticated"])
        self.assertFalse(output["market_odds_or_ev_verified"])

    def test_baseline_cutoff_after_forecast_rejected(self):
        p=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
            "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}]
        r=[{"fixture_id":"a","status":"FT","home_goals":0,"away_goals":0}]
        prior={"probability_over":0.4,"sample_count":200,
               "training_cutoff_utc":"2026-10-15T10:00:00Z","source":"future"}
        with self.assertRaisesRegex(ValueError,"BASELINE_CUTOFF_NOT_BEFORE"):
            audit(p,r,baseline=prior)

    def test_invalid_baseline_rejected_not_silently_used(self):
        p=[{"fixture_id":"a","sealed_at_utc":"2026-10-15T10:00:00Z",
            "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6}]
        r=[{"fixture_id":"a","status":"FT","home_goals":0,"away_goals":0}]
        prior={"probability_over":True,"sample_count":200,
               "training_cutoff_utc":"2026-10-14T00:00:00Z","source":"training"}
        with self.assertRaisesRegex(ValueError,"INVALID_TRAINING_ONLY_BASELINE"):
            audit(p,r,baseline=prior)
        prior["probability_over"]=0.45
        prior["sample_count"]=True
        with self.assertRaisesRegex(ValueError,"INVALID_TRAINING_ONLY_BASELINE"):
            audit(p,r,baseline=prior)

    def test_many_cases_does_not_upgrade_without_baseline(self):
        p=[];r=[]
        for i in range(100):
            key=str(i)
            p.append({"fixture_id":key,"sealed_at_utc":"2026-10-15T10:00:00Z",
                      "kickoff_utc":"2026-10-15T12:00:00Z","probability_over":0.6})
            r.append({"fixture_id":key,"status":"FT","home_goals":1,"away_goals":2})
        output=audit(p,r)
        self.assertEqual(output["calibration_status"],"AUDIT_READY_BASELINE_MISSING")
        self.assertIsNone(output["outperforms_constant_rate_baseline"])
        self.assertEqual(output["production_recommendations"],"DISABLED")

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
