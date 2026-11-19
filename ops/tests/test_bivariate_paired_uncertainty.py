"""Fixed-hypothesis adversarial tests for the exploratory paired CI."""
import copy
import unittest

from ops.bivariate_paired_uncertainty import (
    MARKET_CLASSES, BOOTSTRAP_DRAWS, COMPARISONS, evaluate,
)


def synthetic():
    dates = ["2026-04-01", "2026-04-01", "2026-04-02", "2026-04-03",
             "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-06"]
    observed = {market: [classes[0]] * len(dates)
                for market, classes in MARKET_CLASSES.items()}
    forecasts = {}
    for model, correct_prob in (
            ("dixon_coles", 0.6),
            ("bivariate_poisson", 0.7),
            ("bivariate_poisson_time_decay", 0.7)):
        forecasts[model] = {}
        for market, classes in MARKET_CLASSES.items():
            forecasts[model][market] = [
                {key: (correct_prob if key == classes[0] else
                       (1 - correct_prob) / (len(classes) - 1))
                 for key in classes}
                for _ in dates]
    return dates, observed, forecasts


class PairedUncertaintyTests(unittest.TestCase):
    def test_constant_paired_improvement_and_no_model_promotion(self):
        dates, obs, forecasts = synthetic()
        originals = copy.deepcopy((dates, obs, forecasts))
        report = evaluate(dates, obs, forecasts)
        self.assertEqual(originals, (dates, obs, forecasts))
        self.assertEqual(report["bootstrap_draws"], BOOTSTRAP_DRAWS)
        self.assertEqual(report["paired_fixture_count"], 8)
        self.assertEqual(report["source_calendar_day_clusters"], 6)
        self.assertFalse(report["independent_confirmatory_evidence"])
        self.assertFalse(report["market_odds_or_ev_verified"])
        self.assertFalse(report["model_promoted"])
        self.assertEqual(len(report["comparisons"]), len(COMPARISONS))
        for market in MARKET_CLASSES:
            better = report["comparisons"]["bivariate_poisson_minus_dixon_coles"][market]
            for metric in ("brier", "logloss"):
                stats = better[metric]
                self.assertLess(stats["mean_candidate_minus_baseline"], 0)
                self.assertLess(stats["day_cluster_bootstrap_95pct_interval"][1], 0)
                self.assertFalse(stats["contains_zero"])
            tied = report["comparisons"]["bivariate_poisson_time_decay_minus_bivariate_poisson"][market]
            for metric in ("brier", "logloss"):
                self.assertEqual(tied[metric]["mean_candidate_minus_baseline"], 0)
                self.assertEqual(tied[metric]["day_cluster_bootstrap_95pct_interval"], [0, 0])
                self.assertTrue(tied[metric]["contains_zero"])

    def test_reorder_all_paired_rows_is_identical(self):
        dates, obs, forecasts = synthetic()
        a = evaluate(dates, obs, forecasts)
        permutation = (7, 3, 0, 4, 6, 1, 2, 5)
        reordered_dates = [dates[i] for i in permutation]
        reordered_obs = {market: [values[i] for i in permutation]
                         for market, values in obs.items()}
        reordered_forecasts = {model: {market: [values[i] for i in permutation]
                                     for market, values in markets.items()}
                               for model, markets in forecasts.items()}
        b = evaluate(reordered_dates, reordered_obs, reordered_forecasts)
        self.assertEqual(a, b)

    def test_insufficient_distinct_calendar_days_returns_no_ci(self):
        dates, obs, forecasts = synthetic()
        dates = ["2026-03-01"] * 4 + ["2026-03-02"] * 4
        report = evaluate(dates, obs, forecasts)
        scores = report["comparisons"]["bivariate_poisson_minus_dixon_coles"]["1X2"]
        for metric in ("brier", "logloss"):
            self.assertIsNone(scores[metric]["day_cluster_bootstrap_95pct_interval"])
            self.assertIsNone(scores[metric]["contains_zero"])
            self.assertEqual(scores[metric]["status"],
                             "INSUFFICIENT_DISTINCT_SOURCE_DATES")

    def test_unpaired_fixtures_and_invalid_probability_are_rejected(self):
        dates, obs, forecasts = synthetic()
        del forecasts["dixon_coles"]["TOTAL_OVER_2.75"][-1]
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_MODEL_PAIRED_COHORT"):
            evaluate(dates, obs, forecasts)
        dates, obs, forecasts = synthetic()
        forecasts["bivariate_poisson"]["1X2"][0]["HOME"] = float("nan")
        with self.assertRaises(ValueError):
            evaluate(dates, obs, forecasts)

    def test_invalid_dates_and_outcome_labels_rejected(self):
        dates, obs, forecasts = synthetic()
        dates[0] = "2026-99-99"
        with self.assertRaisesRegex(ValueError, "INVALID_CALENDAR_DAY"):
            evaluate(dates, obs, forecasts)
        dates, obs, forecasts = synthetic()
        obs["1X2"][0] = "HALF_WIN"
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVED_MARKET_CLASS"):
            evaluate(dates, obs, forecasts)


if __name__ == "__main__":
    unittest.main()
