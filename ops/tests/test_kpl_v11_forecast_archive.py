"""Synthetic KPL V11 tests: no actual KPL match, odds, scraping or provider evidence."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research.kpl_v11_forecast_archive import (
    validate_forecast, verify_archive, archive_forecast, chronological_holdout)


BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


def stamp(dt):
    return dt.isoformat().replace("+00:00", "Z")


def forecast(series=0, game=1):
    start = BASE + timedelta(days=series * 3, hours=4 * (game - 1))
    prediction = start - timedelta(minutes=10)
    cutoff = prediction - timedelta(minutes=1)
    return {"prediction_id": f"synthetic-{series}-{game}",
            "series_id": f"synthetic-series-{series}", "game_number": game,
            "team_ids": ["team-a", "team-b"], "predicted_team_id": "team-a",
            "probability": 0.55, "model_version": "synthetic-v1",
            "phase": "PRE_GAME",
            "info_cutoff_at": stamp(cutoff), "forecast_at": stamp(prediction),
            "game_start_at": stamp(start), "status": "RESEARCH_ONLY",
            "evidence": [{"source_id": f"form-{series}-{game}",
                          "kind": "team_form", "subject_game": 0,
                          "published_at": stamp(cutoff - timedelta(minutes=6)),
                          "captured_at": stamp(cutoff - timedelta(minutes=5))}]}


def result(row, *, winner="team-a"):
    end = datetime.fromisoformat(row["game_start_at"].replace("Z", "+00:00")) + timedelta(minutes=25)
    return {"prediction_id": row["prediction_id"], "series_id": row["series_id"],
            "game_number": row["game_number"], "winner_team_id": winner,
            "game_end_at": stamp(end),
            "observed_at": stamp(end + timedelta(minutes=2)),
            "source_id": "synthetic-independent-outcome", "verified": True}


def dataset(series_count=4, games_per_series=2):
    rows = [forecast(s, g) for s in range(series_count)
            for g in range(1, games_per_series + 1)]
    outcomes = [result(r, winner=("team-a" if i % 2 else "team-b"))
                for i, r in enumerate(rows)]
    return rows, outcomes


class TestKPLV11(unittest.TestCase):
    def assert_invalid(self, row, message):
        with self.assertRaisesRegex(ValueError, message):
            validate_forecast(row)

    def test_valid_research_only_forecast(self):
        self.assertTrue(validate_forecast(forecast()))

    def test_reject_future_feature_capture(self):
        row = forecast()
        row["evidence"][0]["captured_at"] = row["game_start_at"]
        self.assert_invalid(row, "post-cutoff evidence")

    def test_reject_feature_published_after_capture(self):
        row = forecast()
        row["evidence"][0]["published_at"] = row["forecast_at"]
        self.assert_invalid(row, "post-cutoff evidence")

    def test_reject_future_game_result(self):
        row = forecast(0, 2)
        row["evidence"][0]["kind"] = "past_result"
        row["evidence"][0]["subject_game"] = 2
        self.assert_invalid(row, "future/current game result/BP")

    def test_reject_future_game_id(self):
        row = forecast(0, 2)
        row["evidence"][0]["subject_game"] = 3
        self.assert_invalid(row, "future game")

    def test_reject_current_bp_in_pregame_phase(self):
        row = forecast(0, 2)
        row["evidence"][0].update(kind="current_bp", subject_game=2)
        self.assert_invalid(row, "current BP before allowed phase")

    def test_accept_bp_locked_phase(self):
        row = forecast(0, 2)
        row["phase"] = "BP_LOCKED"
        row["evidence"][0].update(kind="current_bp", subject_game=2)
        self.assertTrue(validate_forecast(row))

    def test_reject_forecast_after_start(self):
        row = forecast()
        row["forecast_at"] = row["game_start_at"]
        self.assert_invalid(row, "forecast cutoff/time leakage")

    def test_reject_cutoff_after_forecast(self):
        row = forecast()
        row["info_cutoff_at"] = row["game_start_at"]
        self.assert_invalid(row, "forecast cutoff/time leakage")

    def test_reject_outcome_leakage_extra_fields(self):
        row = forecast()
        row["final_winner"] = "team-a"
        self.assert_invalid(row, "invalid forecast fields")

    def test_reject_bool_probability(self):
        row = forecast()
        row["probability"] = True
        self.assert_invalid(row, "invalid probability")

    def test_reject_duplicate_evidence(self):
        row = forecast()
        row["evidence"].append(copy.deepcopy(row["evidence"][0]))
        self.assert_invalid(row, "duplicate evidence")

    def test_archive_round_trip_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.jsonl"
            one, two = forecast(0, 1), forecast(0, 2)
            r1 = archive_forecast(path, one)
            r2 = archive_forecast(path, two)
            verified = verify_archive(path)
            self.assertEqual(verified["records"], [one, two])
            self.assertEqual(verified["head_hash"], r2["head_hash"])
            self.assertNotEqual(r1["head_hash"], r2["head_hash"])
            self.assertFalse(r2["external_immutable_anchor_verified"])

    def test_archive_edit_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.jsonl"
            archive_forecast(path, forecast())
            raw = json.loads(path.read_text().strip())
            raw["forecast"]["probability"] = 0.91
            path.write_text(json.dumps(raw) + "\n")
            with self.assertRaisesRegex(ValueError, "chain mismatch"):
                verify_archive(path)

    def test_archive_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.jsonl"
            archive_forecast(path, forecast())
            with self.assertRaisesRegex(ValueError, "duplicate prediction"):
                archive_forecast(path, forecast())

    def test_archive_rejects_backdate(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.jsonl"
            archive_forecast(path, forecast(1, 1))
            with self.assertRaisesRegex(ValueError, "cannot backdate"):
                archive_forecast(path, forecast(0, 1))

    def test_archive_partial_line_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forecasts.jsonl"
            path.write_text('{"forecast":')
            with self.assertRaisesRegex(ValueError, "truncated"):
                verify_archive(path)

    def test_holdout_series_split_and_baseline(self):
        rows, outcomes = dataset()
        r = chronological_holdout(rows, outcomes, train_fraction=0.5, min_test=2)
        self.assertEqual(r["train"]["count"], 4)
        self.assertEqual(r["holdout"]["count"], 4)
        self.assertEqual(r["train_series"], 2)
        self.assertEqual(r["test_series"], 2)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertAlmostEqual(r["train_prior"], 0.5)
        self.assertEqual(r["holdout"]["count"], r["train_prior_baseline"]["count"])

    def test_holdout_rejects_series_interleaving(self):
        rows, outcomes = dataset()
        rows[2], rows[4] = rows[4], rows[2]
        with self.assertRaises(ValueError):
            chronological_holdout(rows, outcomes, min_test=2)

    def test_holdout_rejects_duplicate_game(self):
        rows, outcomes = dataset()
        rows[1]["prediction_id"] = "some-unique-id"
        rows[1]["game_number"] = rows[0]["game_number"]
        with self.assertRaisesRegex(ValueError, "duplicate game"):
            chronological_holdout(rows, outcomes, min_test=2)

    def test_holdout_training_outcome_not_yet_known(self):
        rows, outcomes = dataset()
        first_test_forecast = rows[4]["forecast_at"]
        outcomes[0]["observed_at"] = first_test_forecast
        r = outcomes[0]
        # End-before-observation remains true: the earlier result has simply
        # been published late, exactly at the first holdout forecast.
        with self.assertRaisesRegex(ValueError, "training outcomes unavailable"):
            chronological_holdout(rows, outcomes, train_fraction=0.5, min_test=2)

    def test_holdout_rejects_result_before_event_finishes(self):
        rows, outcomes = dataset()
        outcomes[0]["game_end_at"] = rows[0]["forecast_at"]
        with self.assertRaisesRegex(ValueError, "result time leakage"):
            chronological_holdout(rows, outcomes, min_test=2)

    def test_holdout_rejects_unverified_result(self):
        rows, outcomes = dataset()
        outcomes[0]["verified"] = False
        with self.assertRaisesRegex(ValueError, "unverified or mismatched result"):
            chronological_holdout(rows, outcomes, min_test=2)

    def test_holdout_unknown_result_id(self):
        rows, outcomes = dataset()
        outcomes[0]["prediction_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "duplicate or unknown result"):
            chronological_holdout(rows, outcomes, min_test=2)

    def test_holdout_too_small(self):
        rows, outcomes = dataset()
        with self.assertRaisesRegex(ValueError, "insufficient series-level holdout"):
            chronological_holdout(rows, outcomes, min_test=6)

    def test_holdout_ignores_test_labels_for_train_prior(self):
        rows, outcomes = dataset()
        a = chronological_holdout(rows, outcomes, train_fraction=0.5, min_test=2)
        for outcome in outcomes[4:]:
            outcome["winner_team_id"] = "team-a"
        b = chronological_holdout(rows, outcomes, train_fraction=0.5, min_test=2)
        self.assertEqual(a["train_prior"], b["train_prior"])
        self.assertEqual(a["train"], b["train"])
        self.assertNotEqual(a["holdout"], b["holdout"])


if __name__ == "__main__":
    unittest.main()
