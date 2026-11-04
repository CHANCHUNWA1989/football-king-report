"""Synthetic temporal leakage tests for uncalibrated research forecasts."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_forecast import poisson_1x2, predict_league, generate


class ShadowForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 4, 0, tzinfo=timezone.utc)
        self.history = []
        teams = ["A", "B", "C", "D", "E", "F"]
        for i in range(48):
            self.history.append({
                "date": (self.now - timedelta(days=i + 1)).date().isoformat(),
                "home": teams[i % 6], "away": teams[(i + 1) % 6],
                "score_ft": [1 + (i % 2), (i % 3 == 0) * 1],
                "status": "FINISHED", "kickoff_utc": None
            })
        self.future = {
            "date": "2026-10-10", "home": "A", "away": "B",
            "kickoff_utc": "2026-10-10T12:00:00+00:00",
            "event_id": "fixture123", "score_ft": None, "status": "SCHEDULED",
        }

    def test_future_predictions_exclude_filled_results(self):
        rows = self.history + [{**self.future, "score_ft": [9, 0]}]
        self.assertEqual(predict_league(rows, "epl", self.now), [])

    def test_future_probability_is_normalized_and_uncalibrated(self):
        result = predict_league(self.history + [self.future], "epl", self.now)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(sum(result[0][k] for k in ("p_home", "p_draw", "p_away")), 1, places=6)
        self.assertFalse(result[0]["calibrated"])
        self.assertEqual(result[0]["production_recommendations"], "DISABLED")

    def test_duplicate_history_does_not_inflate_training(self):
        original = predict_league(self.history + [self.future], "epl", self.now)
        repeated = predict_league(self.history + self.history + [self.future], "epl", self.now)
        self.assertEqual(original, repeated)
        self.assertEqual(original[0]["training_games"], 48)

    def test_conflicting_historical_scores_fail_closed(self):
        changed = {**self.history[0], "score_ft": [9, 9]}
        self.assertEqual(predict_league(self.history + [changed, self.future], "epl", self.now), [])

    def test_conflicting_event_identity_fails_closed(self):
        conflicting = {**self.future, "away": "C"}
        self.assertEqual(predict_league(self.history + [self.future, conflicting], "epl", self.now), [])

    def test_conflicting_kickoff_fails_closed(self):
        conflicting = {**self.future, "kickoff_utc": "2026-10-10T13:00:00+00:00"}
        self.assertEqual(predict_league(self.history + [self.future, conflicting], "epl", self.now), [])

    def test_cutoff_excludes_today(self):
        result = predict_league(self.history + [self.future], "epl", self.now)
        self.assertEqual(result[0]["training_cutoff_local_day"], "2026-10-08")

    def test_unknown_kickoff_excluded(self):
        self.assertEqual(predict_league(self.history + [{**self.future, "kickoff_utc": None}], "epl", self.now), [])

    def test_same_day_result_not_used_for_training(self):
        data = [{**row, "date": "2026-10-09"} for row in self.history] + [self.future]
        self.assertEqual(predict_league(data, "epl", self.now), [])

    def test_need_sufficient_history(self):
        self.assertEqual(predict_league(self.history[:4] + [self.future], "epl", self.now), [])

    def test_future_probabilities_never_prove_profitability(self):
        p = poisson_1x2(1.3, 1.1)
        self.assertAlmostEqual(sum(p), 1, places=6)
        with self.assertRaises(ValueError):
            poisson_1x2(40, 1.2)

    def test_diagnostics_disclose_missing_utc_and_hk_midnight_drop(self):
        missing = {**self.future, "event_id": "missing-utc",
                   "home": "C", "away": "D", "kickoff_utc": None}
        midnight = {**self.future, "event_id": "cross-midnight",
                    "home": "E", "away": "F",
                    "kickoff_utc": "2026-10-10T17:30:00+00:00"}
        diagnostics = {"stale": 1}
        preds = predict_league(self.history + [self.future, missing, midnight],
                               "epl", self.now, diagnostics=diagnostics)
        self.assertEqual(len(preds), 1)
        self.assertEqual(diagnostics["scheduled_source_rows"], 3)
        self.assertEqual(diagnostics["missing_precise_kickoff_utc"], 1)
        self.assertEqual(diagnostics["hk_calendar_date_mismatch"], 1)
        self.assertEqual(diagnostics["eligible_precise_schedules"], 1)
        self.assertEqual(diagnostics["history_unique_games"], 48)
        self.assertEqual(diagnostics["produced_predictions"], len(preds))
        self.assertNotIn("stale", diagnostics)
        self.assertNotIn("score_ft", diagnostics)
        self.assertEqual(preds[0]["production_recommendations"], "DISABLED")

    def test_diagnostics_disclose_insufficient_team_history_without_guessing(self):
        unknown = {**self.future, "event_id": "unknown-clubs",
                   "home": "NeverSeen", "away": "AlsoNeverSeen"}
        diagnostics = {}
        preds = predict_league(self.history + [unknown], "epl", self.now,
                               diagnostics=diagnostics)
        self.assertEqual(preds, [])
        self.assertEqual(diagnostics["eligible_precise_schedules"], 1)
        self.assertEqual(diagnostics["teams_under_three_history_appearances"], 1)
        self.assertEqual(diagnostics["produced_predictions"], 0)

    def test_diagnostics_fail_closed_on_conflicting_identity(self):
        conflicting = {**self.future, "away": "C"}
        diagnostics = {}
        preds = predict_league(self.history + [self.future, conflicting],
                               "epl", self.now, diagnostics=diagnostics)
        self.assertEqual(preds, [])
        self.assertEqual(diagnostics["conflicting_schedule_event_id"], 1)
        self.assertEqual(diagnostics["produced_predictions"], 0)

    def test_diagnostics_surface_in_source_without_changing_probability(self):
        without = predict_league(self.history + [self.future], "epl", self.now)

        def getter(season, league, clock):
            return ({"status": "READY_RESEARCH",
                     "matches": self.history + [self.future]}
                    if league == "epl" else {"status": "HOLD", "matches": []})

        report = generate(now=self.now, getter=getter)
        self.assertEqual(report["predictions"], without)
        item = next(x for x in report["sources"] if x["league"] == "epl")
        self.assertEqual(item["schedule_gate_diagnostics"]["produced_predictions"], 1)
        self.assertEqual(item["schedule_gate_diagnostics"]["eligible_precise_schedules"], 1)
        self.assertEqual(item["schedule_gate_diagnostics"]["history_unique_games"], 48)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_network_failure_stays_hold(self):
        def getter(**kwargs):
            return {"status": "HOLD", "reason": "NO_NETWORK", "matches": []}
        result = generate(now=self.now, getter=getter)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["predictions_count"], 0)


if __name__ == "__main__":
    unittest.main()
