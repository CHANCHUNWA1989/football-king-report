import unittest
from unittest.mock import patch
from ops.private_upstream_penaltyblog_metrics import score_ranked_1x2


class UpstreamMetricTests(unittest.TestCase):
    def test_reject_bad_distribution(self):
        with self.assertRaises(ValueError):
            score_ranked_1x2([{"probabilities": {"H": 0.9, "D": 0.5, "A": 0.2}, "outcome": "H"}])

    def test_reject_invalid_target(self):
        with self.assertRaises(ValueError):
            score_ranked_1x2([{"probabilities": {"H": 0.5, "D": 0.3, "A": 0.2}, "outcome": "X"}])

    def test_real_upstream_metric(self):
        try:
            import penaltyblog.metrics
        except ImportError:
            self.skipTest("optional penaltyblog not installed")
        result = score_ranked_1x2([{"probabilities": {"H": 1.0, "D": 0.0, "A": 0.0}, "outcome": "H"}])
        self.assertAlmostEqual(result["rps"], 0)
        self.assertFalse(result["model_promoted"])
        self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
