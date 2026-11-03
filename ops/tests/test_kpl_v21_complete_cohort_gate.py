"""V21: synthetic-only full-cohort report gate, cannot cherry-pick successful series."""
import copy
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from ops.tests.test_kpl_v20_shadow_trial import (
    BASE, iso, trial_manifest, start_at, decision, outcomes)
from research.kpl_v20_shadow_trial import register_shadow_trial, submit_shadow_decision
from research.kpl_v21_complete_cohort_gate import audit_complete_cohort


class V21CohortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="kpl-v21-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        with patch("research.kpl_v20_shadow_trial._utcnow", return_value=BASE):
            obj = register_shadow_trial(self.root, trial_manifest())
        self.trial = Path(obj["trial_dir"])

    def record(self, sid, game, *, state="FORECAST", p=0.65):
        item = decision(sid, game, state=state, prob=p)
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=start_at(sid, game)-timedelta(minutes=10)):
            submit_shadow_decision(self.trial, item)

    def record_all(self, *, hold_game=None, p=0.65):
        for sid in range(2):
            for game in range(1, 5):
                state = "HOLD" if hold_game == game else "FORECAST"
                self.record(sid, game, state=state, p=p)

    def review(self, data=None, *, min_series=2, min_forecasts=1):
        with patch("research.kpl_v20_shadow_trial._utcnow",
                   return_value=BASE+timedelta(days=5)):
            return audit_complete_cohort(
                self.trial, outcomes() if data is None else data,
                min_completed_series=min_series, min_forecast_maps=min_forecasts)

    def test_complete_claimed_results_only_internal_diagnostic(self):
        self.record_all()
        r = self.review()
        self.assertTrue(r["cohort_all_registered_series_complete"])
        self.assertTrue(r["all_played_map_decisions_present"])
        self.assertTrue(r["all_result_sources_claimed"])
        self.assertTrue(r["internal_diagnostic_cohort_gate_passed"])
        self.assertEqual(r["registered_series_count"], 2)
        self.assertEqual(r["played_maps"], 8)
        self.assertEqual(r["diagnostic_only_not_real_kpl"]["scored_forecasts"], 8)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["real_kpl_accuracy_verified"])
        self.assertFalse(r["results_independently_authenticated"])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["live_execution_allowed"])

    def test_only_easy_completed_series_must_hide_all_metrics(self):
        self.record_all()
        filtered = [r for r in outcomes() if r["series_id"] == "sim-bo-0"]
        result = self.review(filtered)
        self.assertFalse(result["internal_diagnostic_cohort_gate_passed"])
        self.assertIsNone(result["diagnostic_only_not_real_kpl"])
        self.assertIn("REGISTERED_SERIES_UNRESOLVED", result["reasons"])
        self.assertEqual(result["unresolved_registered_series_count"], 1)

    def test_all_results_absent_no_accuracy(self):
        self.record_all()
        r = self.review([])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])
        self.assertEqual(r["completed_series_count"], 0)
        self.assertEqual(r["unresolved_registered_series_count"], 2)
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])

    def test_one_unverified_outcome_suppresses_entire_diagnostic(self):
        self.record_all()
        res = outcomes()
        res[0]["source_status"] = "UNVERIFIED"
        r = self.review(res)
        self.assertEqual(r["unverified_result_maps"], 1)
        self.assertIn("UNVERIFIED_RESULT_IN_REGISTERED_COHORT", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])

    def test_all_unverified_no_real_claim(self):
        self.record_all()
        r = self.review(outcomes(source="UNVERIFIED"))
        self.assertEqual(r["unverified_result_maps"], 8)
        self.assertFalse(r["results_independently_authenticated"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])

    def test_missing_decision_not_silent_sample_filter(self):
        self.record(0, 1)
        r = self.review()
        self.assertEqual(r["missing_pregame_decision_count"], 7)
        self.assertIn("MISSING_PRE_GAME_DECISIONS", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])

    def test_hold_is_recorded_not_filtered_from_coverage(self):
        self.record_all(hold_game=3)
        r = self.review()
        self.assertTrue(r["internal_diagnostic_cohort_gate_passed"])
        self.assertEqual(r["hold_decision_count"], 2)
        self.assertEqual(r["forecast_decision_count"], 6)
        self.assertEqual(r["played_map_forecast_coverage"], 0.75)
        self.assertEqual(r["diagnostic_only_not_real_kpl"]["scored_forecasts"], 6)
        self.assertEqual(r["status"], "HOLD")

    def test_all_hold_without_forecast_does_not_report_accuracy(self):
        self.record_all()
        # Replace fixture by making all local decisions explicit HOLD pregame
        for sid in range(2):
            for game in range(1, 5):
                path = self.trial / "decisions" / f"sim-bo-{sid}-g{game}.json"
                payload = json.loads(path.read_text())
                payload["decision"]["decision"] = "HOLD"
                payload["decision"]["probability_a"] = None
                payload["decision"]["reason_code"] = "MODEL_UNCALIBRATED"
                path.write_text(json.dumps(payload) + "\n")
        r = self.review()
        self.assertEqual(r["hold_decision_count"], 8)
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])
        self.assertIn("INSUFFICIENT_RECORDED_FORECASTS", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])

    def test_orphan_fifth_forecast_after_bo7_four_zero_cannot_be_ignored(self):
        self.record_all()
        self.record(0, 5)
        r = self.review()
        self.assertIn("UNSETTLED_OR_ORPHAN_RECORDED_DECISIONS", r["reasons"])
        self.assertEqual(r["extra_recorded_decision_count"], 1)
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])

    def test_altered_result_source_claim_is_not_official(self):
        self.record_all()
        res = outcomes()
        for row in res:
            row["source_id"] = "official-looking-name"
        r = self.review(res)
        self.assertTrue(r["internal_diagnostic_cohort_gate_passed"])
        self.assertFalse(r["results_independently_authenticated"])
        self.assertFalse(r["real_kpl_accuracy_verified"])

    def test_sample_minimum_unmet_masks_metrics(self):
        self.record_all()
        r = self.review(min_series=40, min_forecasts=120)
        self.assertIn("MINIMUM_COHORT_SAMPLE_NOT_MET", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])

    def test_no_historical_predictions_never_emits_wager(self):
        r = self.review([])
        self.assertNotIn("wager", r)
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["status"], "HOLD")

    def test_invalid_duplicate_winner_records_safe_hold(self):
        self.record_all()
        res = outcomes()
        res.append(copy.deepcopy(res[0]))
        r = self.review(res)
        self.assertIn("INVALID_SETTLEMENT_INPUT", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])

    def test_forged_kickoff_does_not_inflate_confidence(self):
        self.record_all()
        res = outcomes()
        res[0]["game_start_at"] = iso(start_at(0, 1)+timedelta(hours=1))
        r = self.review(res)
        self.assertIn("INVALID_SETTLEMENT_INPUT", r["reasons"])
        self.assertFalse(r["internal_diagnostic_cohort_gate_passed"])

    def test_tampered_manifest_fail_closed(self):
        self.record(0, 1)
        p = self.trial / "manifest.json"
        data = json.loads(p.read_text())
        data["model_version"] = "rewritten"
        p.write_text(json.dumps(data)+"\n")
        r = self.review([])
        self.assertIn("INVALID_SETTLEMENT_INPUT", r["reasons"])
        self.assertEqual(r["status"], "HOLD")

    def test_wrong_minimum_threshold_fails_closed(self):
        self.record_all()
        r = self.review(min_series=0)
        self.assertIn("INVALID_SHADOW_GATE_POLICY", r["reasons"])
        self.assertIsNone(r["diagnostic_only_not_real_kpl"])

    def test_incomplete_series_played_maps_still_visible(self):
        self.record_all()
        res = [r for r in outcomes() if
               r["series_id"] == "sim-bo-0" or
               (r["series_id"] == "sim-bo-1" and r["game_number"] in (1, 2))]
        result = self.review(res)
        self.assertEqual(result["observed_result_maps"], 6)
        self.assertEqual(result["completed_series_count"], 1)
        self.assertEqual(result["unresolved_registered_series_count"], 1)
        self.assertIsNone(result["diagnostic_only_not_real_kpl"])

    def test_no_false_independent_provenance_even_if_gate_passes(self):
        self.record_all()
        r = self.review()
        self.assertFalse(r["trial_registration_independently_witnessed"])
        self.assertFalse(r["decisions_independently_witnessed"])
        self.assertFalse(r["source_usage_rights_independently_verified"])
        self.assertFalse(r["real_kpl_accuracy_verified"])


if __name__ == "__main__":
    unittest.main()
