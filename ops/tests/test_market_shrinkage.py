"""Regression tests for conservative market shrinkage candidate."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_shrinkage import blend, compare, score
import market_shrinkage


class MarketShrinkageTests(unittest.TestCase):
    def test_shared_ranked_probability_score_has_ordered_hand_computed_values(self):
        for probabilities, outcome, expected in (
                ([1., 0., 0.], 0, 0.), ([1., 0., 0.], 1, .5),
                ([1., 0., 0.], 2, 1.), ([.5, .3, .2], 1, .145),
                ([.333, .333, .333], 1, 1 / 9)):
            with self.subTest(probabilities=probabilities, outcome=outcome):
                self.assertAlmostEqual(
                    market_shrinkage.ranked_probability_score(probabilities, outcome), expected)

    def test_shared_rps_rejects_invalid_probabilities_and_outcomes(self):
        for probabilities, outcome in (([True, 0, 0], 0), ([.5, .5], 0),
                                       ([float("nan"), 0, 1], 0), ([1.1, 0, -.1], 0),
                                       ([1, 0, 0], True), ([1, 0, 0], -1),
                                       ([1, 0, 0], 3), ([1, 0, 0], 1.0)):
            with self.subTest(probabilities=probabilities, outcome=outcome), self.assertRaises(ValueError):
                market_shrinkage.ranked_probability_score(probabilities, outcome)

    def test_market_blend(self):
        self.assertEqual(blend([.8, .1, .1], [.2, .3, .5], 1), [.2, .3, .5])
        self.assertEqual(blend([.8, .1, .1], [.2, .3, .5], 0), [.8, .1, .1])
        self.assertAlmostEqual(sum(blend([.8, .1, .1], [.2, .3, .5])), 1)

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            blend([.8, .1, .1], [.2, .3, .5], 1.5)
        with self.assertRaises(ValueError):
            blend([True, .1, .9], [.2, .3, .5])

    def test_chronological_holdout_research_only(self):
        rows = [
            {"kickoff": f"2026-10-{d:02d}", "p": [.7, .2, .1], "m": [.2, .2, .6], "y": 2}
            for d in range(1, 9)
        ]
        result = compare(rows)
        self.assertEqual(result["holdout_n"], 2)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "INSUFFICIENT_HOLDOUT_EVIDENCE")
        self.assertLess(result["holdout_comparison"]["1.00"]["log_loss"],
                        result["holdout_comparison"]["0.00"]["log_loss"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["holdout_is_independent_forward_sample"])

    def test_rps_respects_ordering_and_market_baseline(self):
        rows = [{"p": [1., 0., 0.], "m": [0., 0., 1.], "y": 2}]
        self.assertAlmostEqual(score(rows, 0)["rps"], 1.0)
        self.assertAlmostEqual(score(rows, 1)["rps"], 0.0)
        self.assertAlmostEqual(score(rows, .5)["rps"], .25)

    def test_empty(self):
        self.assertEqual(compare([])["status"], "HOLD")
        self.assertIsNone(score([], .75))


if __name__ == "__main__":
    unittest.main()
