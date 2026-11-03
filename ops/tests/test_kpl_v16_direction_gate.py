"""V16 synthetic tests: no genuine KPL odds, live feed or calibration claim."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from research.kpl_v16_direction_gate import (
    bo7_series_probability, evaluate_point_in_time_calibration,
    screen_next_map_direction)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ts(t):
    return t.isoformat().replace("+00:00", "Z")


def synthetic_history(n_series=44, n_games=3, *, strong=True):
    records = []
    for s in range(n_series):
        for g in range(1, n_games + 1):
            t = BASE + timedelta(days=s * 4, hours=g)
            y = (s + g) % 2
            p = (0.98 if y == 1 else 0.02) if strong else 0.5
            records.append({
                "series_id": f"synthetic-bo-{s:03d}", "game_number": g,
                "team_a": "synthetic-A", "team_b": "synthetic-B",
                "model_version": "research-frozen-v1",
                "model_frozen_at": ts(BASE - timedelta(days=20)),
                "forecast_at": ts(t - timedelta(minutes=10)),
                "game_start_at": ts(t),
                "outcome_observed_at": ts(t + timedelta(minutes=40)),
                "baseline_captured_at": ts(t - timedelta(minutes=15)),
                "model_probability_a": p,
                "baseline_probability_a": 0.5,
                "outcome_a": y,
                "held_out": True,
                "baseline_source_id": "synthetic-independent-coinflip"})
    return records


def candidate():
    t = BASE + timedelta(days=300)
    return {
        "series_id": "wb-edgm-not-a-real-feed", "game_number": 4,
        "team_a": "EDGM", "team_b": "WB", "score_a": 2, "score_b": 1,
        "model_version": "research-frozen-v1",
        "forecast_at": ts(t - timedelta(minutes=7)),
        "game_start_at": ts(t),
        "info_cutoff_at": ts(t - timedelta(minutes=8)),
        "phase": "BP_LOCKED", "bp_complete": True,
        "bp_attested_externally": True, "probability_a": 0.90,
        "interval_low_a": 0.85, "interval_high_a": 0.95}


class DirectionGateV16Tests(unittest.TestCase):
    def test_neutral_scoreline_edgm_two_one_not_next_map_superiority(self):
        self.assertAlmostEqual(bo7_series_probability(2, 1, [0.5] * 4), 0.6875)
        self.assertAlmostEqual(bo7_series_probability(1, 2, [0.5] * 4), 0.3125)

    def test_model_old_545_conditional_series_is_near_75(self):
        self.assertAlmostEqual(
            bo7_series_probability(2, 1, [0.545] * 4), 0.750, delta=0.015)

    def test_future_map_probabilities_required(self):
        with self.assertRaisesRegex(ValueError, "missing map probabilities"):
            bo7_series_probability(2, 1, [])

    def test_terminal_score(self):
        self.assertEqual(bo7_series_probability(4, 2, []), 1.0)
        self.assertEqual(bo7_series_probability(2, 4, []), 0.0)

    def test_bad_score_rejected(self):
        with self.assertRaises(ValueError):
            bo7_series_probability(3, 5, [0.5])

    def test_historic_calibration_synthetic_pass_is_not_real_validation(self):
        r = evaluate_point_in_time_calibration(
            synthetic_history(), as_of=ts(BASE + timedelta(days=300)))
        self.assertTrue(r["structural_calibration_gate_passed"], r)
        self.assertEqual(r["series_count"], 44)
        self.assertEqual(r["map_count"], 132)
        self.assertGreater(r["paired_brier_gain"], 0)
        self.assertGreater(r["series_cluster_bootstrap_gain_lower_95_one_sided"], 0)
        self.assertFalse(r["real_kpl_calibration_verified"])
        self.assertEqual(r["status"], "HOLD")

    def test_missing_historic_evidence_fails(self):
        r = screen_next_map_direction(candidate(), [])
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["research_direction"])

    def test_tiny_three_map_history_not_enough(self):
        r = screen_next_map_direction(candidate(), synthetic_history(1, 3))
        self.assertIn("INSUFFICIENT_INDEPENDENT_SERIES_OR_MAPS", r["reasons"])

    def test_wb_edgm_direction_545_must_not_be_published(self):
        c = candidate()
        c["probability_a"] = 0.545
        c["interval_low_a"] = 0.47
        c["interval_high_a"] = 0.62
        c["bp_attested_externally"] = False
        c["bp_complete"] = False
        r = screen_next_map_direction(c, synthetic_history())
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["research_direction"])
        self.assertIn("MISSING_VERIFIED_FOURTH_MAP_BP", r["reasons"])
        self.assertIn("INDEPENDENT_BP_ATTESTATION_MISSING", r["reasons"])
        self.assertIn("UNCERTAINTY_INTERVAL_DOES_NOT_SUPPORT_DIRECTION", r["reasons"])

    def test_missing_bp_even_with_big_p_holds(self):
        c = candidate()
        c["bp_complete"] = False
        c["phase"] = "PRE_GAME"
        r = screen_next_map_direction(c, synthetic_history())
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["research_direction"])

    def test_wide_interval_no_direction_even_with_stacked_history(self):
        c = candidate()
        c["probability_a"] = 0.54
        c["interval_low_a"] = 0.45
        c["interval_high_a"] = 0.65
        r = screen_next_map_direction(c, synthetic_history())
        self.assertIsNone(r["research_direction"])
        self.assertEqual(r["status"], "HOLD")

    def test_qualified_synthetic_signal_is_shadow_only_not_bet(self):
        r = screen_next_map_direction(candidate(), synthetic_history())
        self.assertEqual(r["research_direction"], "EDGM")
        self.assertEqual(r["direction_kind"], "SHADOW_ONLY")
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["real_kpl_calibration_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["live_execution_allowed"])

    def test_opposite_research_direction_requires_upper_bound_below_45(self):
        c = candidate()
        c["probability_a"] = 0.10
        c["interval_low_a"] = 0.03
        c["interval_high_a"] = 0.14
        r = screen_next_map_direction(c, synthetic_history())
        self.assertEqual(r["research_direction"], "WB")
        self.assertEqual(r["status"], "HOLD")

    def test_unmatched_model_version_holds(self):
        c = candidate()
        c["model_version"] = "not-frozen-research-v99"
        r = screen_next_map_direction(c, synthetic_history())
        self.assertIn("MODEL_VERSION_HAS_NO_MATCHING_HOLDOUT", r["reasons"])
        self.assertIsNone(r["research_direction"])

    def test_future_historical_outcomes_rejected(self):
        h = synthetic_history()
        h[0]["outcome_observed_at"] = ts(BASE + timedelta(days=400))
        with self.assertRaisesRegex(ValueError, "future or backfilled history"):
            evaluate_point_in_time_calibration(h, as_of=ts(BASE + timedelta(days=300)))
        r = screen_next_map_direction(candidate(), h)
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["research_direction"])

    def test_not_held_out_is_rejected(self):
        h = synthetic_history()
        h[0]["held_out"] = False
        with self.assertRaisesRegex(ValueError, "outcome-leaking"):
            evaluate_point_in_time_calibration(h, as_of=ts(BASE + timedelta(days=300)))

    def test_baseline_backfilled_after_forecast_rejected(self):
        h = synthetic_history()
        h[0]["baseline_captured_at"] = h[0]["game_start_at"]
        with self.assertRaisesRegex(ValueError, "future or backfilled history"):
            evaluate_point_in_time_calibration(h, as_of=ts(BASE + timedelta(days=300)))

    def test_no_gain_over_baseline_rejected(self):
        h = synthetic_history(strong=False)
        r = evaluate_point_in_time_calibration(h, as_of=ts(BASE + timedelta(days=300)))
        self.assertFalse(r["structural_calibration_gate_passed"])
        self.assertIn("NO_SERIES_CLUSTERED_EVIDENCE_OF_BASELINE_GAIN", r["reasons"])

    def test_single_team_orientation_per_series(self):
        h = synthetic_history()
        h[1]["team_a"], h[1]["team_b"] = h[1]["team_b"], h[1]["team_a"]
        with self.assertRaisesRegex(ValueError, "team orientation"):
            evaluate_point_in_time_calibration(h, as_of=ts(BASE + timedelta(days=300)))

    def test_false_precision_does_not_indicate_market_edge(self):
        result = screen_next_map_direction(candidate(), synthetic_history())
        self.assertFalse(result["positive_ev_verified"])

    def test_bad_candidate_scoreline_fails_closed(self):
        c = candidate()
        c["score_a"] = 4
        c["score_b"] = -1
        r = screen_next_map_direction(c, synthetic_history())
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["research_direction"])


if __name__ == "__main__":
    unittest.main()
