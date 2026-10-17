import unittest
from shared.unified_prediction_evaluation import evaluate

P = dict(prediction_id="p1", system="football", event_id="e1", created_at="2026-10-17T10:00:00+08:00", model_version="v1", market="1X2", selection="home", probability=0.6, odds=2.0, status="RESEARCH_ONLY")
O = dict(prediction_id="p1", outcome=1, actual_result_at="2026-10-17T12:00:00+08:00", verified=True, source="test-fixture")

class EvaluationTests(unittest.TestCase):
    def test_pending_not_counted(self):
        r = evaluate([P], [])
        self.assertEqual((r["evaluated"], r["pending"], r["mean_brier"]), (0, 1, None))
    def test_verified_score(self):
        self.assertAlmostEqual(evaluate([P], [O])["mean_brier"], 0.16)
    def test_unverified_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, verified=False)])
    def test_duplicate_predictions_rejected(self):
        with self.assertRaises(ValueError): evaluate([P, P], [])
    def test_unknown_result_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, prediction_id="missing")])
    def test_no_roi_without_trades(self):
        self.assertIsNone(evaluate([P], [O])["roi"])
if __name__ == "__main__":
    unittest.main()
