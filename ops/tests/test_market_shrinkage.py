"""Regression tests for conservative market shrinkage candidate."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_shrinkage import blend, compare, score
import market_shrinkage


class MarketShrinkageTests(unittest.TestCase):
    def test_same_kickoff_cohort_is_valid_when_entirely_in_holdout(self):
        rows = [{"kickoff": value, "p": [.7, .2, .1], "m": [.2, .2, .6], "y": 2}
                for value in ("2026-10-01", "2026-10-02", "2026-10-03", "2026-10-03")]
        result = compare(rows, holdout_fraction=.5)
        self.assertEqual(result["holdout_n"], 2)
        self.assertEqual(result["holdout_distinct_dates"], 1)
        self.assertEqual(result["status"], "HOLD")
        self.assertIs(result["holdout_is_independent_forward_sample"], False)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_same_utc_kickoff_cannot_straddle_train_holdout_boundary(self):
        base = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        for kickoffs in (
                ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-03"],
                [base, base + timedelta(days=1), base + timedelta(days=2),
                 (base + timedelta(days=2)).astimezone(timezone(timedelta(hours=8)))],
                ["2026-10-01T12:00:00Z", "2026-10-02T12:00:00Z",
                 "2026-10-03T12:00:00Z", "2026-10-03T20:00:00+08:00"]):
            rows = [{"kickoff": value, "p": [.7, .2, .1], "m": [.2, .2, .6], "y": 2}
                    for value in kickoffs]
            with self.subTest(kickoffs=kickoffs), self.assertRaises(ValueError):
                compare(rows)

    def test_holdout_order_uses_utc_instants_and_preserves_input(self):
        kickoffs = ["2026-10-01T10:00:00Z", "2026-10-02T09:30:00Z",
                    "2026-10-02T11:00:00+02:00", "2026-10-02T09:45:00Z"]
        rows = [{"kickoff": value, "p": [1., 0., 0.], "m": [0., 0., 1.], "y": 0}
                for value in kickoffs]
        rows[2]["p"] = [0., 0., 1.]  # 09:00 UTC, before the actual holdout.
        result = compare(rows)
        self.assertEqual(result["holdout_n"], 1)
        self.assertEqual(result["holdout_comparison"]["0.00"]["brier"], 0.)
        self.assertEqual([row["kickoff"] for row in rows], kickoffs)
        self.assertIs(result["holdout_is_independent_forward_sample"], False)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_holdout_date_coverage_counts_utc_days(self):
        rows = [{"kickoff": value, "p": [.7, .2, .1], "m": [.2, .2, .6], "y": 2}
                for value in ("2026-10-01T09:00:00Z", "2026-10-02T09:00:00Z",
                              "2026-10-03T00:30:00Z", "2026-10-02T21:45:00-03:00")]
        result = compare(rows, holdout_fraction=.5)
        self.assertEqual(result["holdout_n"], 2)
        self.assertEqual(result["holdout_distinct_dates"], 1)

    def test_unknown_or_naive_kickoff_clocks_are_rejected(self):
        for value in ("2026-10-03T12:00:00", datetime(2026, 10, 3, 12),
                      "not-a-date", ""):
            rows = [{"kickoff": value, "p": [.7, .2, .1], "m": [.2, .2, .6], "y": 2}
                    for _ in range(4)]
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(rows)

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
