"""Synthetic-only KPL V20 prospective shadow protocol and no-cherry-pick tests."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.kpl_v20_shadow_trial import (
    register_shadow_trial, submit_shadow_decision, audit_shadow_trial)

BASE = datetime(2026, 12, 1, 12, tzinfo=timezone.utc)


def iso(t):
    return t.isoformat().replace("+00:00", "Z")


def start_at(series, game):
    return BASE + timedelta(hours=3 + (game-1)*2, days=series*2)


def trial_manifest(series_count=2):
    return {
        "trial_id": "synthetic-shadow-v20",
        "registration_at": iso(BASE),
        "model_version": "fixed-shadow-v1",
        "model_frozen_at": iso(BASE-timedelta(days=1)),
        "series": [
            {"series_id": f"sim-bo-{s}", "team_ids": ["a", "b"],
             "first_game_start_at": iso(start_at(s, 1)),
             "schedule_source_id": "synthetic-schedule"}
            for s in range(series_count)]}


def decision(series, game, *, state="FORECAST", prob=0.65):
    start = start_at(series, game)
    return {
        "series_id": f"sim-bo-{series}", "game_number": game,
        "team_ids": ["a", "b"], "decision": state,
        "probability_a": prob if state == "FORECAST" else None,
        "reason_code": ("SHADOW_FORECAST" if state == "FORECAST"
                        else "MODEL_UNCALIBRATED"),
        "phase": "PRE_GAME", "info_cutoff_at": iso(start-timedelta(minutes=11)),
        "forecast_at": iso(start-timedelta(minutes=10)),
        "game_start_at": iso(start), "basis_source_id": "simulated-pre-map"}


def outcomes(series_count=2, *, source="SOURCE_ASSERTED"):
    result = []
    for s in range(series_count):
        for g in range(1, 5):
            started = start_at(s, g)
            result.append({
                "series_id": f"sim-bo-{s}", "game_number": g,
                "team_ids": ["a", "b"], "winner_team_id": "a",
                "game_start_at": iso(started),
                "game_end_at": iso(started+timedelta(minutes=30)),
                "observed_at": iso(started+timedelta(minutes=40)),
                "source_id": "synthetic-source",
                "source_status": source})
    return result


class KPLV20Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kpl-v20-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = trial_manifest()
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            info = register_shadow_trial(self.root, self.manifest)
        self.directory = Path(info["trial_dir"])

    def record(self, series, game, *, state="FORECAST", prob=0.65, at=None):
        rec = decision(series, game, state=state, prob=prob)
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=at or start_at(series, game)-timedelta(minutes=10)):
            return submit_shadow_decision(self.directory, rec)

    def register_all(self, *, one_hold=False):
        for s in range(2):
            for g in range(1, 5):
                self.record(s, g, state="HOLD" if one_hold and g == 3 else "FORECAST")

    def audit(self, records=None):
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=BASE+timedelta(days=5)):
            return audit_shadow_trial(
                self.directory, outcomes() if records is None else records)

    def test_registration_preserves_universe_and_hold(self):
        obj = json.loads((self.directory/"manifest.json").read_text())
        self.assertEqual(obj["series"], self.manifest["series"])
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=BASE+timedelta(days=5)):
            report = audit_shadow_trial(self.directory, [])
        self.assertEqual(report["registered_series_count"], 2)
        self.assertEqual(report["unresolved_registered_series_count"], 2)
        self.assertEqual(report["status"], "HOLD")
        self.assertFalse(report["trial_registration_independently_witnessed"])

    def test_duplicate_trial_registration_fails(self):
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            with self.assertRaises(FileExistsError):
                register_shadow_trial(self.root, self.manifest)

    def test_old_registration_clock_rejected(self):
        manifest = trial_manifest()
        manifest["trial_id"] = "older"
        manifest["registration_at"] = iso(BASE-timedelta(days=1))
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            with self.assertRaisesRegex(ValueError, "not near local"):
                register_shadow_trial(self.root, manifest)

    def test_registration_after_first_kickoff_rejected(self):
        manifest = trial_manifest()
        manifest["trial_id"] = "too-late"
        manifest["registration_at"] = iso(start_at(0, 1)+timedelta(minutes=1))
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=start_at(0, 1)+timedelta(minutes=1)):
            with self.assertRaisesRegex(ValueError, "schedule not after registration"):
                register_shadow_trial(self.root, manifest)

    def test_duplicate_series_manifest_rejected(self):
        manifest = trial_manifest()
        manifest["series"].append(copy.deepcopy(manifest["series"][0]))
        manifest["trial_id"] = "duplicate-series"
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            with self.assertRaisesRegex(ValueError, "duplicate or malformed"):
                register_shadow_trial(self.root, manifest)

    def test_model_freeze_after_registration_rejected(self):
        manifest = trial_manifest()
        manifest["model_frozen_at"] = iso(BASE+timedelta(minutes=1))
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            with self.assertRaisesRegex(ValueError, "model not frozen"):
                register_shadow_trial(self.root, manifest)

    def test_path_traversal_series_rejected(self):
        manifest = trial_manifest()
        manifest["series"][0]["series_id"] = "../other"
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            with self.assertRaisesRegex(ValueError, "malformed"):
                register_shadow_trial(self.root, manifest)

    def test_forecast_pre_game_recorded_create_only(self):
        r = self.record(0, 1)
        self.assertEqual(r["decision"], "FORECAST")
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["externally_witnessed"])
        with self.assertRaises(FileExistsError):
            self.record(0, 1)

    def test_hold_pre_game_with_no_probability(self):
        r = self.record(0, 1, state="HOLD")
        self.assertEqual(r["decision"], "HOLD")
        self.assertEqual(r["status"], "HOLD")

    def test_cannot_force_probability_on_hold(self):
        rec = decision(0, 1, state="HOLD")
        rec["probability_a"] = 0.61
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=start_at(0, 1)-timedelta(minutes=10)):
            with self.assertRaisesRegex(ValueError, "HOLD must not"):
                submit_shadow_decision(self.directory, rec)

    def test_unknown_series_rejected(self):
        rec = decision(0, 1)
        rec["series_id"] = "unlisted-bo"
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=start_at(0, 1)-timedelta(minutes=10)):
            with self.assertRaisesRegex(ValueError, "unknown registered series"):
                submit_shadow_decision(self.directory, rec)

    def test_game_two_requires_prior_game_decision(self):
        with self.assertRaisesRegex(ValueError, "prior game has no recorded"):
            self.record(0, 2)

    def test_future_or_backfilled_forecast_time_rejected(self):
        with self.assertRaisesRegex(ValueError, "late, backdated"):
            self.record(0, 1, at=BASE)

    def test_after_first_advertised_start_rejected(self):
        rec = decision(0, 1)
        rec["game_start_at"] = iso(start_at(0, 1)+timedelta(hours=1))
        rec["forecast_at"] = iso(start_at(0, 1)+timedelta(minutes=1))
        rec["info_cutoff_at"] = iso(start_at(0, 1))
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=start_at(0, 1)+timedelta(minutes=1)):
            with self.assertRaisesRegex(ValueError, "game one already scheduled"):
                submit_shadow_decision(self.directory, rec)

    def test_missing_decisions_are_counted_not_erased(self):
        self.record(0, 1)
        report = self.audit()
        self.assertEqual(report["completed_played_maps"], 8)
        self.assertEqual(report["missing_pregame_decision_count"], 7)
        self.assertEqual(report["forecast_decision_count"], 1)
        self.assertAlmostEqual(report["played_map_decision_coverage"], 1/8)
        self.assertEqual(report["status"], "HOLD")

    def test_holds_remain_in_denominator(self):
        self.register_all(one_hold=True)
        report = self.audit()
        self.assertEqual(report["completed_played_maps"], 8)
        self.assertEqual(report["missing_pregame_decision_count"], 0)
        self.assertEqual(report["hold_decision_count"], 2)
        self.assertEqual(report["forecast_decision_count"], 6)
        self.assertEqual(report["diagnostic_only_not_real_kpl"]["scored_forecasts"], 6)
        self.assertEqual(report["played_map_forecast_coverage"], 6/8)

    def test_all_forecasts_diagnostic_only(self):
        self.register_all()
        r = self.audit()
        metric = r["diagnostic_only_not_real_kpl"]
        self.assertEqual(metric["scored_forecasts"], 8)
        self.assertAlmostEqual(metric["brier"], (1-.65)**2)
        self.assertAlmostEqual(metric["uniform_50_brier"], .25)
        self.assertEqual(metric["direction_accuracy"], 1.0)
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["results_independently_authenticated"])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["live_execution_allowed"])

    def test_unverified_result_is_not_scored(self):
        self.register_all()
        data = outcomes(source="UNVERIFIED")
        r = self.audit(data)
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])
        self.assertEqual(r["forecast_decision_count"], 8)

    def test_future_result_rejected(self):
        self.register_all()
        data = outcomes()
        data[0]["observed_at"] = iso(BASE+timedelta(days=15))
        with self.assertRaisesRegex(ValueError, "result unavailable"):
            self.audit(data)

    def test_wrong_team_result_rejected(self):
        self.register_all()
        data = outcomes()
        data[0]["winner_team_id"] = "bad-team"
        with self.assertRaisesRegex(ValueError, "invalid outcome identity"):
            self.audit(data)

    def test_duplicate_outcome_rejected(self):
        self.register_all()
        data = outcomes()
        data.append(copy.deepcopy(data[0]))
        with self.assertRaisesRegex(ValueError, "duplicate outcome"):
            self.audit(data)

    def test_result_after_series_already_won_rejected(self):
        self.register_all()
        data = outcomes()
        extra = copy.deepcopy(data[3])
        extra["game_number"] = 5
        extra["game_start_at"] = iso(start_at(0, 5))
        extra["game_end_at"] = iso(start_at(0, 5)+timedelta(minutes=30))
        extra["observed_at"] = iso(start_at(0, 5)+timedelta(minutes=40))
        data.append(extra)
        with self.assertRaisesRegex(ValueError, "after BO7 already won"):
            self.audit(data)

    def test_one_series_incomplete_has_unresolved_coverage(self):
        self.register_all()
        only_first = [x for x in outcomes() if x["series_id"] == "sim-bo-0"]
        result = self.audit(only_first)
        self.assertEqual(result["completed_series_count"], 1)
        self.assertEqual(result["unresolved_registered_series_count"], 1)
        self.assertEqual(result["completed_played_maps"], 4)

    def test_tampered_manifest_after_decision_is_rejected(self):
        self.record(0, 1)
        obj = json.loads((self.directory/"manifest.json").read_text())
        obj["model_version"] = "changed-after-registration"
        (self.directory/"manifest.json").write_text(json.dumps(obj)+"\n")
        with self.assertRaisesRegex(ValueError, "manifest binding mismatch"):
            self.audit([])

    def test_tampered_probability_invalid_recorded_at_rejected(self):
        self.record(0, 1)
        path = self.directory/"decisions"/"sim-bo-0-g1.json"
        obj = json.loads(path.read_text())
        obj["decision"]["forecast_at"] = iso(BASE)
        path.write_text(json.dumps(obj)+"\n")
        with self.assertRaisesRegex(ValueError, "late, backdated"):
            self.audit([])

    def test_claimed_official_source_never_promotes_trust(self):
        self.register_all()
        data = outcomes()
        for item in data:
            item["source_id"] = "allegedly-official"
        result = self.audit(data)
        self.assertFalse(result["results_independently_authenticated"])
        self.assertFalse(result["schedule_independently_authenticated"])
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
