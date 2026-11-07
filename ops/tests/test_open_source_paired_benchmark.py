"""Synthetic-only tests for paired bootstrap research evaluator."""
import unittest
from ops.open_source_paired_benchmark import compare


def row(key, y, p, m, verified=False):
    return {"key": key, "y": y, "p": p, "m": m,
            "fixture_result_source_independently_verified": verified,
            "kickoff_utc": "2026-11-08T20:00:00+00:00",
            "forecast_utc": "2026-11-07T20:00:00+00:00",
            "market_utc": "2026-11-07T19:00:00+00:00"}


class PairedBenchmarkTests(unittest.TestCase):
    def test_empty_is_hold(self):
        result = compare([])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["sample_count"], 0)

    def test_identical_probabilities_have_zero_difference(self):
        r = compare([row("a", 0, [.7, .2, .1], [.7, .2, .1])], bootstrap_reps=100)
        self.assertEqual(r["metrics"]["log_loss"]["model_minus_market"], 0)
        self.assertEqual(r["paired_difference_95pct_bootstrap_ci"]["log_loss"], [0, 0])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_market_better(self):
        r = compare([row("a", 0, [.2, .4, .4], [.8, .1, .1]),
                     row("b", 2, [.6, .3, .1], [.1, .1, .8])], bootstrap_reps=100)
        self.assertGreater(r["metrics"]["log_loss"]["model_minus_market"], 0)
        self.assertEqual(r["independently_verified_result_count"], 0)

    def test_unverified_result_stays_hold(self):
        r = compare([row("a", 0, [.7, .2, .1], [.7, .2, .1])], bootstrap_reps=10)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["data_quality_pass"])

    def test_verified_chronology_research_only(self):
        r = compare([row("a", 0, [.7, .2, .1], [.7, .2, .1], verified=True)], bootstrap_reps=10)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertTrue(r["data_quality_pass"])

    def test_post_kickoff_forecast_rejected(self):
        bad = row("a", 0, [.7, .2, .1], [.7, .2, .1], verified=True)
        bad["forecast_utc"] = "2026-11-09T00:00:00+00:00"
        r = compare([bad], bootstrap_reps=10)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["invalid_or_missing_chronology_count"], 1)

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            compare([row("a", 0, [.7, .2, .1], [.7, .2, .1])] * 2)

    def test_deterministic(self):
        rows = [row(str(i), i % 3, [.4, .3, .3], [.3, .4, .3]) for i in range(10)]
        self.assertEqual(compare(rows, bootstrap_reps=100), compare(rows, bootstrap_reps=100))

    def test_invalid_probability_not_counted(self):
        r = compare([row("a", 0, [.9, .9, -.8], [.5, .3, .2])], bootstrap_reps=10)
        self.assertEqual(r["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
