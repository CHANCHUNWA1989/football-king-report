import math
import unittest
from research_quality.probability_diagnostics import score_forecasts

class ProbabilityDiagnosticsTests(unittest.TestCase):
    def test_perfect_prediction(self):
        result = score_forecasts([{"p": [1.0, 0.0, 0.0], "y": 0}])
        self.assertEqual(result["brier"], 0.0)
        self.assertEqual(result["log_loss"], 0.0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_uniform_baseline(self):
        result = score_forecasts([{"p": [1/3]*3, "y": 2}])
        self.assertAlmostEqual(result["brier"], 2/3)
        self.assertAlmostEqual(result["log_loss"], math.log(3))

    def test_empty_data_not_success(self):
        result = score_forecasts([])
        self.assertIsNone(result["brier"])
        self.assertEqual(result["status"], "INSUFFICIENT_DATA")

    def test_bad_probabilities_rejected(self):
        for p in ([0.8, 0.8, -0.6], [float("nan"), 0, 1], [True, 0, 0], [0.5, 0.5]):
            with self.subTest(p=p), self.assertRaises(ValueError):
                score_forecasts([{"p": p, "y": 0}])

    def test_invalid_outcomes_rejected(self):
        for y in (-1, 3, True, "0"):
            with self.subTest(y=y), self.assertRaises(ValueError):
                score_forecasts([{"p": [1, 0, 0], "y": y}])

    def test_sample_cap(self):
        with self.assertRaises(ValueError):
            score_forecasts([{}] * 20001)
