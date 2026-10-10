"""Retrospective date-cutoff replay must never masquerade as prospective picks."""
import copy
import hashlib
import json
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_backtest import (
    build, parse_archive, replay, draw_adjust, frequency_baseline,
    evaluate_cohort, block_ci, MIN_HOLDOUT, choose_prior_blend, blend_with_prior,
)


class RetrospectiveReplayTests(unittest.TestCase):
    def setUp(self):
        start = date(2025, 8, 1)
        clubs = ["A", "B", "C", "D", "E", "F"]
        self.fixture_rows = []
        # A deliberately synthetic, valid history used ONLY in unit tests.
        for i in range(120):
            self.fixture_rows.append({
                "date": (start + timedelta(days=i)).isoformat(),
                "team1": clubs[i % len(clubs)],
                "team2": clubs[(i + 1) % len(clubs)],
                "score": {"ft": [i % 4, (i + 1) % 3]},
            })

    def test_parse_accepts_finished_ft_and_rejects_future_without_guessing_time(self):
        doc = {"name": "Synthetic", "matches": copy.deepcopy(self.fixture_rows)}
        matches, missing = parse_archive(doc)
        self.assertEqual(len(matches), 120)
        self.assertEqual(missing, {})
        self.assertTrue(all("kickoff_utc" not in row for row in matches))

    def test_model_is_replayed_using_only_previous_calendar_day_results(self):
        matches, _ = parse_archive({"matches": self.fixture_rows})
        first, skipped = replay(matches, "epl", "2025-26")
        self.assertGreater(len(first), 50)
        self.assertGreaterEqual(skipped["initial_less_than_30_games"], 30)
        # Altering a future-day final score cannot change any probability
        # issued in the date-only retrospective at earlier calendar cutoffs.
        changed = copy.deepcopy(matches)
        changed[-1]["score_ft"] = [20, 0]
        second, _ = replay(changed, "epl", "2025-26")
        self.assertEqual([x["original"] for x in first],
                         [x["original"] for x in second])
        self.assertEqual(first[-1]["training_games"], 119)

    def test_earliest_team_seen_only_after_30_results_is_skipped(self):
        rows = copy.deepcopy(self.fixture_rows)
        rows[-1]["team1"] = "Unseen Club"
        matches, _ = parse_archive({"matches": rows})
        samples, excluded = replay(matches, "epl", "2025-26")
        self.assertEqual(excluded["not_predicted_with_prior_history"], 1)
        self.assertTrue(all(sum(row["original"]) > 0.999 for row in samples))

    def test_predeclared_draw_challenger_moves_exact_three_points(self):
        old = [0.6, 0.22, 0.18]
        new = draw_adjust(old)
        self.assertAlmostEqual(sum(new), 1.0)
        self.assertAlmostEqual(new[1], old[1] + 0.03)
        self.assertGreater(old[0], new[0])
        self.assertEqual(max(range(3), key=new.__getitem__), 0)

    def test_frequency_baseline_uses_only_past_scores(self):
        past = [{"score_ft": [1, 0]} for _ in range(4)]
        p = frequency_baseline(past)
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], 0.45)
        self.assertEqual(len(p), 3)

    def test_baseline_report_and_honest_uncertainty(self):
        matches, _ = parse_archive({"matches": self.fixture_rows})
        rows, _ = replay(matches, "epl", "2025-26")
        e = evaluate_cohort(rows)
        self.assertGreater(e["n"], 50)
        self.assertEqual(e["original"]["n"], len(rows))
        self.assertEqual(len(e["coverage_at_confidence_cutoffs"]), 4)
        self.assertTrue(math.isfinite(e["original"]["mean_log_loss"]))
        self.assertFalse(e["original"]["draw_calibration_gap"] is None)
        self.assertIsNotNone(block_ci(rows, "draw_adjust", repetitions=1000))

    def test_prior_shrink_weight_chosen_exclusively_from_development_data(self):
        rows = [
            {"original": [.6, .2, .2], "league_frequency": [.3, .4, .3],
             "y": i % 3} for i in range(70)
        ]
        fit = choose_prior_blend(rows)
        self.assertEqual(fit["basis"], "2024_25_DEVELOPMENT_LOG_LOSS_ONLY")
        self.assertIn(fit["weight"], (0.0, .1, .2, .3, .4))
        self.assertEqual(len(fit["scores"]), 5)
        original = fit.copy()
        extra_holdout_that_must_be_ignored = [
            {"original": [.1, .1, .8], "league_frequency": [.8, .1, .1],
             "y": 0} for _ in range(500)]
        self.assertEqual(choose_prior_blend(rows), original)
        # The alternative holdout records are deliberately never passed to fit.
        self.assertEqual(len(extra_holdout_that_must_be_ignored), 500)

    def test_prior_blend_never_invents_or_renormalizes_bad_probabilities(self):
        blended = blend_with_prior([.7, .2, .1], [.4, .3, .3], .2)
        self.assertAlmostEqual(sum(blended), 1.0)
        self.assertAlmostEqual(blended[0], .64)
        with self.assertRaises(ValueError):
            blend_with_prior([.7, .2, .9], [.4, .3, .3], .2)
        with self.assertRaises(ValueError):
            blend_with_prior([.7, .2, .1], [.4, .3, .3], .8)

    def test_archive_shortfall_stays_research_disabled(self):
        doc = {"matches": self.fixture_rows}
        result = build({("2025-26", "epl"): (doc, hashlib.sha256(
            json.dumps(doc).encode()).hexdigest())})
        self.assertEqual(result["holdout_season_samples"],
                         result["cohorts"]["2025-26"]["n"])
        self.assertLess(result["holdout_season_samples"], MIN_HOLDOUT)
        self.assertEqual(result["interpretation"],
                         "INSUFFICIENT_RETROSPECTIVE_HOLDOUT_COVERAGE")
        self.assertFalse(result["live_point_in_time_forecasts_verified"])
        self.assertFalse(result["betting_roi_estimable"])
        self.assertFalse(result["automatic_model_promotion"])
        self.assertFalse(result["prior_blend_automatic_promotion_permitted"])
        self.assertFalse(result["prior_blend_uses_holdout_labels_for_tuning"])
        self.assertTrue(result["holdout_has_already_been_inspected_previously"])
        self.assertIsNotNone(result["prior_blend_holdout"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertTrue(result["replay_adapter_time_is_not_a_real_kickoff"])


if __name__ == "__main__":
    unittest.main()
