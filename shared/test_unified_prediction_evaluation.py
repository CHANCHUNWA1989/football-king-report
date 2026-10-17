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
    def test_accuracy_denominator_counts_verified_only(self):
        self.assertEqual(evaluate([P], [O])["accuracy_denominator"], 1)
        self.assertEqual(evaluate([P], [])["accuracy_denominator"], 0)
    def test_half_probability_excluded_from_directional_accuracy(self):
        tie = dict(P, probability=.5)
        for actual in (0, 1):
            r = evaluate([tie], [dict(O, outcome=actual)])
            self.assertEqual(r["correct_at_50pct"], 0)
            self.assertEqual(r["accuracy_denominator"], 0)
            self.assertEqual(r["abstained_at_50pct"], 1)
            self.assertAlmostEqual(r["mean_brier"], .25)
    def test_unverified_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, verified=False)])
    def test_duplicate_predictions_rejected(self):
        with self.assertRaises(ValueError): evaluate([P, P], [])
    def test_unknown_result_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, prediction_id="missing")])
    def test_no_roi_without_trades(self):
        self.assertIsNone(evaluate([P], [O])["roi"])
    def test_missing_source_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, source="")])
    def test_duplicate_outcome_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [O, O])
    def test_nonbinary_outcome_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, outcome=2)])
    def test_result_before_forecast_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, actual_result_at="2026-10-17T09:00:00+08:00")])
    def test_boolean_result_rejected(self):
        with self.assertRaises(ValueError): evaluate([P], [dict(O, outcome=True)])
    def test_pending_does_not_score(self):
        self.assertEqual(evaluate([P], [])["correct_at_50pct"], 0)
    def test_systems_separate(self):
        q = dict(P, prediction_id="q1", system="quant", probability=.2)
        r = evaluate([P, q], [O])
        self.assertEqual(r["by_system"]["football"]["evaluated"], 1)
        self.assertEqual(r["by_system"]["quant"]["pending"], 1)
        self.assertIsNone(r["by_system"]["quant"]["mean_brier"])
    def test_small_sample_warning(self):
        r = evaluate([P], [O])
        self.assertEqual(r["sample_warning"], "INSUFFICIENT_VERIFIED_OUTCOMES")
        self.assertEqual(r["minimum_sample_for_reporting"], 100)
    def test_excessive_input_rejected(self):
        with self.assertRaises(ValueError): evaluate([P] * 100001, [])
        with self.assertRaises(ValueError): evaluate([], [O] * 100001)
    def test_oversized_jsonl_rejected_before_parsing(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from shared.unified_prediction_evaluation import evaluate_jsonl
        with TemporaryDirectory() as d:
            large = Path(d) / "oversized.jsonl"
            empty = Path(d) / "empty.jsonl"
            with large.open("wb") as handle:
                handle.truncate(32_000_001)
            empty.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError): evaluate_jsonl(large, empty)
    def test_no_predictions(self):
        self.assertEqual(evaluate([], [])["by_system"], {})

if __name__ == "__main__":
    unittest.main()
