import copy
import unittest
from ops.dynamic_2026_date_split_audit import (
    evaluate, audit, MODELS, CLASSES, BOOTSTRAPS,
)
from ops.tests.test_bivariate_real_2026_paired_oos import rows, FakePackage, FakeModel


class DynamicDateOnlyAuditTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_paired_same_cohort_all_markets_and_uncertainty(self):
        training, unseen = rows()
        immutable = copy.deepcopy((training, unseen))
        report = evaluate(training, unseen, model_module=FakePackage,
                          min_train=30, min_test=5)
        self.assertEqual((training, unseen), immutable)
        self.assertEqual(report["training_real_matches"], 40)
        self.assertEqual(report["same_eligible_heldout_games"], 8)
        self.assertEqual(report["source_test_rows"], 8)
        self.assertEqual(report["bootstrap_draws"], BOOTSTRAPS)
        self.assertFalse(report["test_scores_passed_to_model_fit"])
        self.assertTrue(report["date_only_retrospective_no_publisher_time_authentication"])
        self.assertEqual(report["tested_models"], list(MODELS))
        self.assertEqual(set(report["per_model_scores"]), set(MODELS))
        for markets in report["per_model_scores"].values():
            self.assertEqual(set(markets), set(CLASSES))
            for metric in markets.values():
                self.assertEqual(metric["n"], 8)
                self.assertGreaterEqual(metric["mean_brier"], 0)
                self.assertGreaterEqual(metric["mean_logloss"], 0)
        ci = report["dynamic_minus_dixon_coles_paired_date_cluster_CI95"]
        self.assertEqual(set(ci), set(CLASSES))
        for market in ci:
            for metric in ("brier", "logloss"):
                self.assertEqual(len(ci[market][metric]["interval_95pct"]), 2)
                self.assertEqual(ci[market][metric]["distinct_date_clusters"], 8)
        self.assertEqual(len(FakeModel.calls), 2)
        self.assertEqual([len(call["home_goals"]) for call in FakeModel.calls], [40,40])

    def test_totals_calibration_and_structural_grades(self):
        train, test = rows()
        report = evaluate(train, test, model_module=FakePackage,
                          min_train=30, min_test=5)
        n = len(test)
        totals = [sum(r["score_ft"]) for r in test]
        for model, markets in report["per_model_scores"].items():
            for line in ("2.5", "2.75", "3.0"):
                item = markets["OVER_" + line]
                counts = item["observed_class_counts"]
                probs = item["mean_forecast_class_probability"]
                self.assertEqual(sum(counts.values()), n)
                self.assertAlmostEqual(sum(probs.values()), 1.0, places=5)
                self.assertEqual(counts["FULL_LOSS"], sum(t <= 2 for t in totals))
                self.assertEqual(counts["HALF_LOSS"], 0)
                self.assertEqual(probs["HALF_LOSS"], 0)
                boundary = {"2.5": "FULL_WIN", "2.75": "HALF_WIN", "3.0": "PUSH"}[line]
                self.assertEqual(counts[boundary], sum(t >= 3 if line == "2.5" else t == 3 for t in totals))
            a, b, c = [markets["OVER_" + l]["mean_forecast_class_probability"]
                       for l in ("2.5", "2.75", "3.0")]
            self.assertAlmostEqual(a["FULL_WIN"], b["FULL_WIN"] + b["HALF_WIN"], places=6)
            self.assertAlmostEqual(b["HALF_WIN"], c["PUSH"], places=6)
            self.assertAlmostEqual(b["FULL_WIN"], c["FULL_WIN"], places=6)

    def test_2026_test_results_never_enter_fitting(self):
        train, test = rows()
        evaluate(train, test, model_module=FakePackage, min_train=30, min_test=5)
        saved_inputs = copy.deepcopy(FakeModel.calls)
        FakeModel.calls = []
        test[0]["score_ft"] = [9, 0]
        new = evaluate(train, test, model_module=FakePackage,
                       min_train=30, min_test=5)
        self.assertEqual(saved_inputs, FakeModel.calls)
        self.assertNotIn(9, FakeModel.calls[0]["home_goals"])
        self.assertEqual(new["same_eligible_heldout_games"], 8)

    def test_invalid_year_and_duplicate_score_are_fail_closed(self):
        for testname in ("future_train", "old_test", "duplicate", "bool"):
            training, heldout = rows()
            if testname == "future_train":
                training[0]["date"] = "2026-01-05"
            elif testname == "old_test":
                heldout[0]["date"] = "2025-11-30"
            elif testname == "duplicate":
                heldout[-1] = copy.deepcopy(heldout[0])
            else:
                heldout[0]["score_ft"][0] = True
            with self.subTest(testname=testname), self.assertRaises(ValueError):
                evaluate(training, heldout, model_module=FakePackage,
                         min_train=30, min_test=5)
        self.assertEqual(FakeModel.calls, [])

    def test_no_team_history_does_not_emit_model_success(self):
        train, test = rows()
        for row in test:
            row["away"] = "brand_new_team"
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_PREDECLARED_TEAM_COVERAGE"):
            evaluate(train, test, model_module=FakePackage,
                     min_train=30, min_test=5)

    def test_missing_actual_public_source_never_promotes(self):
        report = audit(reader=lambda: (_ for _ in ()).throw(
            ValueError("unavailable")), model_module=FakePackage)
        self.assertEqual(report["reason"], "REAL_DYNAMIC_2026_AUDIT_BLOCKED")
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["original_holdout_untouched_confirmatory"])
        self.assertFalse(report["model_promoted"])
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
