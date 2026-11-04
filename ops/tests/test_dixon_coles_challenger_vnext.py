"""Development-only Dixon-Coles chronological fitting; synthetic data only."""
import copy
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dixon_coles_challenger_vnext import (
    MODEL_ID, RHO_GRID, audit_fit, audit_shadow_forecast,
    fit_development, shadow_forecast,
)

UTC = timezone.utc
CUTOFF = "2026-10-15T00:00:00Z"


def stamp(dt):
    return dt.isoformat().replace("+00:00", "Z")


def data(n=30):
    rows = []
    for i in range(n):
        kickoff = datetime(2026, 9, 1, 20, tzinfo=UTC) + timedelta(days=i)
        score = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 1), (2, 2)][i % 6]
        rows.append({
            "fixture_id": "match-%03d" % i,
            "kickoff_utc": stamp(kickoff),
            "forecast_utc": stamp(kickoff - timedelta(minutes=90)),
            "inputs_available_utc": stamp(kickoff - timedelta(minutes=95)),
            "result_available_utc": stamp(kickoff + timedelta(minutes=120)),
            "home_goals": score[0], "away_goals": score[1],
            "expected_home_goals": 1.35, "expected_away_goals": 1.1,
            "input_sha256": ("%064x" % (i + 1)),
        })
    return rows


def manifest(rows):
    return {
        "fixture_ids": [r["fixture_id"] for r in rows],
        "manifest_declared_utc": "2026-10-10T00:00:00Z",
        "development_cohort_id": "synthetic-fixed-complete-v1",
    }


def prospective_args():
    return {
        "fixture_id": "future-fixture-001",
        "kickoff_utc": "2026-10-22T20:00:00Z",
        "forecast_utc": "2026-10-22T18:40:00Z",
        "inputs_available_utc": "2026-10-22T18:35:00Z",
        "home_rate": 1.4, "away_rate": 1.15,
        "input_sha256": "e" * 64,
    }


class DixonColesDevelopmentTests(unittest.TestCase):
    def test_development_selection_explicitly_in_sample_and_disabled(self):
        rows = data()
        result = fit_development(rows, manifest(rows), fit_cutoff_utc=CUTOFF)
        self.assertEqual(result["status"], "DEVELOPMENT_ONLY")
        self.assertEqual(result["model_id"], MODEL_ID)
        self.assertIn(result["selected_rho"], RHO_GRID)
        self.assertEqual(result["development_n"], 30)
        self.assertEqual(len(result["grid_scores"]), len(RHO_GRID))
        self.assertEqual(result["development_metric"], "IN_SAMPLE_SCORELINE_LOG_LOSS")
        self.assertFalse(result["model_calibrated"])
        self.assertFalse(result["out_of_sample_accuracy_improvement_verified"])
        self.assertFalse(result["source_results_independently_verified"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_fitted_rho_minimizes_prespecified_development_loss(self):
        rows = data()
        result = fit_development(rows, manifest(rows), fit_cutoff_utc=CUTOFF)
        scores = {p["rho"]: p["mean_development_scoreline_log_loss"]
                  for p in result["grid_scores"]}
        self.assertAlmostEqual(scores[result["selected_rho"]], min(scores.values()), places=12)

    def test_results_deterministic_under_permuted_development_order(self):
        rows = data()
        a = fit_development(rows, manifest(rows), fit_cutoff_utc=CUTOFF)
        b = fit_development(list(reversed(rows)), manifest(rows), fit_cutoff_utc=CUTOFF)
        self.assertEqual(a, b)

    def test_prospective_shadow_uses_frozen_rho_and_has_no_ev(self):
        rows = data()
        fit = fit_development(rows, manifest(rows), fit_cutoff_utc=CUTOFF)
        result = shadow_forecast(fit, **prospective_args())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["selected_rho"], fit["selected_rho"])
        self.assertAlmostEqual(sum(result["probabilities_1x2"].values()), 1, places=10)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["out_of_sample_accuracy_improvement_verified"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["positive_ev_verified"])

    def test_no_forecast_before_fit_cutoff(self):
        fitted = fit_development(data(), manifest(data()), fit_cutoff_utc=CUTOFF)
        args = prospective_args()
        args.update({
            "kickoff_utc": "2026-10-14T20:00:00Z",
            "forecast_utc": "2026-10-14T18:45:00Z",
            "inputs_available_utc": "2026-10-14T18:40:00Z",
        })
        self.assertEqual(audit_shadow_forecast(fitted, **args)["reason"],
                         "PROSPECTIVE_FORECAST_TIME_OR_IDENTITY_CONFLICT")

    def test_late_model_source_input_must_be_rejected(self):
        fitted = fit_development(data(), manifest(data()), fit_cutoff_utc=CUTOFF)
        args = prospective_args()
        args["inputs_available_utc"] = "2026-10-22T19:00:00Z"
        self.assertEqual(audit_shadow_forecast(fitted, **args)["status"], "HOLD")

    def test_one_future_label_in_training_is_rejected(self):
        rows = data()
        rows[0]["result_available_utc"] = "2026-11-03T22:00:00Z"
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["reason"],
                         "TRAINING_OUTCOME_UNAVAILABLE_AT_FIT_CUTOFF")

    def test_label_not_available_ninety_minutes_after_kickoff_rejected(self):
        rows = data()
        rows[0]["result_available_utc"] = "2026-09-01T20:20:00Z"
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["status"], "HOLD")

    def test_training_forecast_is_not_recreated_after_kickoff(self):
        rows = data()
        rows[0]["forecast_utc"] = "2026-09-01T20:01:00Z"
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["reason"],
                         "TRAINING_FORECAST_LOOKAHEAD")

    def test_training_source_cannot_be_younger_than_forecast(self):
        rows = data()
        rows[0]["inputs_available_utc"] = "2026-09-01T19:59:00Z"
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["reason"],
                         "TRAINING_FORECAST_LOOKAHEAD")

    def test_duplicate_fixture_identifier_rejected(self):
        rows = data()
        rows[1]["fixture_id"] = rows[0]["fixture_id"]
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["status"], "HOLD")

    def test_incomplete_manifest_universe_rejected(self):
        rows = data()
        m = manifest(rows)
        m["fixture_ids"].pop()
        self.assertEqual(audit_fit(rows, m, fit_cutoff_utc=CUTOFF)["reason"],
                         "INCOMPLETE_OR_LATE_MANIFEST")

    def test_manifest_not_existing_before_fit_rejected(self):
        rows = data()
        m = manifest(rows)
        m["manifest_declared_utc"] = "2026-11-04T00:00:00Z"
        self.assertEqual(audit_fit(rows, m, fit_cutoff_utc=CUTOFF)["status"], "HOLD")

    def test_less_than_30_samples_rejected(self):
        rows = data(29)
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["reason"],
                         "INSUFFICIENT_OR_EXCESSIVE_DEVELOPMENT_COHORT")

    def test_known_score_label_out_of_range_rejected(self):
        rows = data()
        rows[0]["home_goals"] = True
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["status"], "HOLD")
        rows = data()
        rows[0]["away_goals"] = 99
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["status"], "HOLD")

    def test_finite_goal_rates_required(self):
        rows = data()
        rows[0]["expected_home_goals"] = float("nan")
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["status"], "HOLD")

    def test_unexpected_market_or_final_label_in_forecast_rejected(self):
        rows = data()
        rows[0]["bookmaker_odds"] = 1.8
        self.assertEqual(audit_fit(rows, manifest(rows), fit_cutoff_utc=CUTOFF)["reason"],
                         "INVALID_DEVELOPMENT_SCHEMA")

    def test_invalid_fitted_record_or_rho_not_allowed_to_predict(self):
        fitted = fit_development(data(), manifest(data()), fit_cutoff_utc=CUTOFF)
        fitted["selected_rho"] = 0.04
        self.assertEqual(audit_shadow_forecast(fitted, **prospective_args())["status"], "HOLD")

    def test_no_assessment_metrics_are_claimed_from_fit(self):
        fitted = fit_development(data(), manifest(data()), fit_cutoff_utc=CUTOFF)
        self.assertNotIn("holdout_score", fitted)
        self.assertNotIn("win_rate", fitted)
        self.assertNotIn("roi", fitted)

    def test_bad_manifest_digest_rejected_in_prospective(self):
        fitted = fit_development(data(), manifest(data()), fit_cutoff_utc=CUTOFF)
        fitted["declared_manifest_sha256_unattested"] = "forged"
        self.assertEqual(audit_shadow_forecast(fitted, **prospective_args())["status"], "HOLD")

    def test_all_failures_keep_production_disabled(self):
        f = audit_fit([], {}, fit_cutoff_utc=CUTOFF)
        self.assertEqual(f["status"], "HOLD")
        self.assertEqual(f["production_recommendations"], "DISABLED")
        self.assertFalse(f["positive_ev_verified"])


if __name__ == "__main__":
    unittest.main()
