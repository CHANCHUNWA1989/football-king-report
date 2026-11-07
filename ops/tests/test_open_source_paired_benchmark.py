"""Synthetic-only tests for paired bootstrap research evaluator."""
import unittest
from ops.open_source_paired_benchmark import compare


def row(key, y, p, m, verified=False):
    return {"key": key, "y": y, "p": p, "m": m,
            "fixture_result_source_independently_verified": verified}


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
