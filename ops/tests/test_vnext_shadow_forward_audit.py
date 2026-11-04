"""Synthetic forward-only paired challenger and quote metadata audit tests."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_shadow_forward_audit import (
    audit_paired, audit_quote_metadata, evaluate_paired, _score,
)

UTC = timezone.utc
EVAL = "2026-10-05T00:00:00Z"


def stamp(t):
    return t.isoformat().replace("+00:00", "Z")


def synthetic_case(i=0):
    kickoff = datetime(2026, 8, 1, 20, tzinfo=UTC) + timedelta(days=i)
    forecast = kickoff - timedelta(minutes=90)
    source = forecast - timedelta(minutes=1)
    raw_id = f"synthetic-match-{i:04d}"
    models = {
        "baseline": {
            "model_id": "poisson-A",
            "forecast_utc": stamp(forecast),
            "inputs_available_utc": stamp(source),
            "input_sha256": "a" * 64,
            "probabilities_1x2": [0.45, 0.30, 0.25],
            "calibrated": False, "production_recommendations": "DISABLED",
        },
        "challenger": {
            "model_id": "candidate-DC",
            "forecast_utc": stamp(forecast),
            "inputs_available_utc": stamp(source),
            "input_sha256": "b" * 64,
            "probabilities_1x2": [0.65, 0.20, 0.15],
            "calibrated": False, "production_recommendations": "DISABLED",
        },
    }
    return {
        "pair": {
            "fixture_id": raw_id, "kickoff_utc": stamp(kickoff),
            "as_of_utc": stamp(forecast), "models": models,
        },
        "result": {
            "fixture_id": raw_id, "home_goals": 2, "away_goals": 1,
            "result_received_utc": stamp(kickoff + timedelta(hours=3)),
            "result_source": "synthetic-result",
            "raw_sha256": "c" * 64,
            "independently_authenticated": False,
        },
    }


def synthetic_rows(n=30):
    return [synthetic_case(i) for i in range(n)]


def quote():
    return {
        "fixture_id": "synthetic-match-0000",
        "bookmaker": "example-book",
        "quote_id": "quote-001",
        "market": "asian_handicap",
        "side": "HOME", "line": -0.75,
        "decimal_odds": 2.0,
        "scope": "REGULATION_90_MINUTES_INCLUDING_STOPPAGE",
        "provider_updated_utc": "2026-08-01T18:29:30Z",
        "captured_utc": "2026-08-01T18:29:35Z",
        "received_utc": "2026-08-01T18:29:40Z",
        "available_utc": "2026-08-01T18:29:45Z",
        "raw_sha256": "d" * 64,
        "licensed_and_executable_independently_verified": False,
    }


def check_quote(q=None):
    return audit_quote_metadata(q if q is not None else quote(),
                                fixture_id="synthetic-match-0000",
                                kickoff_utc="2026-08-01T20:00:00Z",
                                decision_utc="2026-08-01T18:30:00Z")


class PairedForwardAuditTests(unittest.TestCase):
    def test_30_paired_matches_produce_exploratory_only_metrics(self):
        report = evaluate_paired(synthetic_rows(), evaluated_utc=EVAL)
        self.assertEqual(report["status"], "EXPLORATORY_ONLY")
        self.assertEqual(report["cohort_n_independent_fixture_ids"], 30)
        self.assertEqual(report["model_ids"], {
            "baseline": "poisson-A", "challenger": "candidate-DC"})
        self.assertAlmostEqual(report["metric"]["baseline"]["mean_brier"], .455, places=12)
        self.assertGreater(report["paired_baseline_minus_challenger_log_loss"], 0)
        self.assertGreater(report["paired_baseline_minus_challenger_brier"], 0)
        self.assertEqual(len(report["self_asserted_cohort_hash"]), 64)
        self.assertFalse(report["independent_result_authentication"])
        self.assertFalse(report["true_prospective_holdout_verified"])
        self.assertFalse(report["model_accuracy_gain_verified"])
        self.assertFalse(report["ev_or_roi_verified"])
        self.assertFalse(report["model_promotable"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_brier_and_log_loss_conventional_three_class_score(self):
        ll, bs, rps = _score((.5, .25, .25), 0)
        self.assertAlmostEqual(ll, .6931471805599453)
        self.assertAlmostEqual(bs, .375)
        self.assertAlmostEqual(rps, .078125)

    def test_calibration_bins_count_fixtures_by_class(self):
        r = evaluate_paired(synthetic_rows(), evaluated_utc=EVAL)
        for model in ("baseline", "challenger"):
            for side in r["metric"][model]["calibration"]:
                self.assertEqual(sum(b["n"] for b in side["bins"]), 30)
        self.assertEqual(r["metric"]["challenger"]["calibration"][0]["bins"][3]["n"], 30)

    def test_29_cases_hold_as_insufficient_not_success(self):
        r = audit_paired(synthetic_rows(29), evaluated_utc=EVAL)
        self.assertEqual(r["reason"], "INSUFFICIENT_INDEPENDENT_FIXTURES")
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_duplicate_fixture_and_two_times_cannot_be_double_counted(self):
        rows = synthetic_rows()
        rows[-1] = copy.deepcopy(rows[0])
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"],
                         "DUPLICATE_FIXTURE_OR_SNAPSHOT")

    def test_missing_result_is_atomic_hold_not_skipped(self):
        rows = synthetic_rows()
        del rows[-1]["result"]
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_result_fixture_mismatch_fails(self):
        rows = synthetic_rows()
        rows[0]["result"]["fixture_id"] = "wrong-match"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"],
                         "UNVERIFIED_RESULT_CLAIMS_OR_IDENTITY")

    def test_future_settlement_not_known_at_evaluation(self):
        rows = synthetic_rows()
        rows[0]["result"]["result_received_utc"] = "2026-10-10T00:00:00Z"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"],
                         "RESULT_NOT_AVAILABLE_AT_EVALUATION")

    def test_result_received_too_early_is_rejected(self):
        rows = synthetic_rows()
        rows[0]["result"]["result_received_utc"] = "2026-08-01T21:00:00Z"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_model_inputs_after_forecast_are_rejected(self):
        rows = synthetic_rows()
        rows[0]["pair"]["models"]["baseline"]["inputs_available_utc"] = "2026-08-01T19:59:00Z"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"],
                         "FUTURE_INPUT_OR_UNPAIRED_CLOCK")

    def test_forecasts_unpaired_as_of_or_not_prematch(self):
        for field, value in (("forecast_utc", "2026-08-01T18:31:00Z"),
                             ("forecast_utc", "2026-08-01T20:00:00Z")):
            with self.subTest(value=value):
                rows = synthetic_rows()
                rows[0]["pair"]["models"]["challenger"][field] = value
                self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_same_model_id_blocks_self_comparison(self):
        rows = synthetic_rows()
        rows[0]["pair"]["models"]["challenger"]["model_id"] = "poisson-A"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"], "DUPLICATED_MODEL_ID")

    def test_mixed_model_versions_do_not_silently_pool(self):
        rows = synthetic_rows()
        rows[1]["pair"]["models"]["challenger"]["model_id"] = "candidate-D2"
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"], "MIXED_MODEL_VERSIONS")

    def test_future_label_leakage_to_pair_schema_fails(self):
        rows = synthetic_rows()
        rows[0]["pair"]["home_goals"] = 2
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"], "INVALID_PAIR_SCHEMA")

    def test_forged_calibration_and_recommendation_refused(self):
        for field, value in (("calibrated", True),
                             ("production_recommendations", "ENABLED")):
            with self.subTest(field=field):
                rows = synthetic_rows()
                rows[0]["pair"]["models"]["baseline"][field] = value
                self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_probability_nan_zero_negative_and_unnormalized_refused(self):
        for p in ([float("nan"), .3, .7], [0, .4, .6],
                  [-.1, .4, .7], [.5, .5, .5], [True, .2, .8]):
            with self.subTest(p=str(p)):
                rows = synthetic_rows()
                rows[0]["pair"]["models"]["baseline"]["probabilities_1x2"] = p
                self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_result_authenticated_claim_refused(self):
        rows = synthetic_rows()
        rows[0]["result"]["independently_authenticated"] = True
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["status"], "HOLD")

    def test_valid_different_score_classes_are_scored(self):
        rows = synthetic_rows()
        rows[0]["result"]["away_goals"] = 2  # draw
        rows[1]["result"]["away_goals"] = 3  # away wins
        r = evaluate_paired(rows, evaluated_utc=EVAL)
        self.assertEqual(r["status"], "EXPLORATORY_ONLY")
        self.assertGreater(r["metric"]["baseline"]["mean_log_loss"], 0)

    def test_repeat_evaluation_is_deterministic(self):
        a = evaluate_paired(synthetic_rows(), evaluated_utc=EVAL)
        b = evaluate_paired(synthetic_rows(), evaluated_utc=EVAL)
        self.assertEqual(a, b)


class QuoteEvidenceTests(unittest.TestCase):
    def test_complete_quote_still_holds_ev(self):
        r = check_quote()
        self.assertEqual(r["status"], "HOLD")
        self.assertTrue(r["quote_metadata_consistent"])
        self.assertFalse(r["market_executable_verified"])
        self.assertFalse(r["ev_or_roi_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_quote_received_after_decision_rejected(self):
        q = quote()
        q["received_utc"] = "2026-08-01T18:31:00Z"
        q["available_utc"] = "2026-08-01T18:31:01Z"
        self.assertEqual(check_quote(q)["reason"], "FUTURE_OR_OUT_OF_ORDER_QUOTE")

    def test_quote_expired_upstream_rejected(self):
        q = quote()
        q["provider_updated_utc"] = "2026-08-01T18:20:00Z"
        self.assertEqual(check_quote(q)["reason"], "STALE_QUOTE")

    def test_quote_scope_mismatch_rejected(self):
        q = quote()
        q["scope"] = "REMAINDER_ONLY"
        self.assertEqual(check_quote(q)["reason"], "UNATTESTED_QUOTE_OR_WRONG_SCOPE")

    def test_quote_even_with_certified_flag_cannot_self_certify(self):
        q = quote()
        q["licensed_and_executable_independently_verified"] = True
        self.assertEqual(check_quote(q)["status"], "HOLD")
        self.assertFalse(check_quote(q)["quote_metadata_consistent"])

    def test_quote_non_quarter_line_and_invalid_price_rejected(self):
        for name, val in (("line", -.3), ("line", True),
                          ("decimal_odds", float("nan")), ("decimal_odds", 1.0)):
            with self.subTest(name=name, val=str(val)):
                q = quote()
                q[name] = val
                self.assertFalse(check_quote(q)["quote_metadata_consistent"])

    def test_quote_wrong_fixture_and_missing_bookmaker_rejected(self):
        q = quote()
        q["fixture_id"] = "other-fixture"
        self.assertFalse(check_quote(q)["quote_metadata_consistent"])
        q = quote()
        q["bookmaker"] = ""
        self.assertFalse(check_quote(q)["quote_metadata_consistent"])

    def test_quote_illegal_1x2_line_rejected(self):
        q = quote()
        q["market"] = "h2h"
        q["side"] = "HOME"
        self.assertFalse(check_quote(q)["quote_metadata_consistent"])

    def test_quote_no_price_leak_into_shadow_evaluation(self):
        rows = synthetic_rows()
        rows[0]["pair"]["models"]["baseline"]["decimal_odds"] = 9.99
        self.assertEqual(audit_paired(rows, evaluated_utc=EVAL)["reason"],
                         "INVALID_FROZEN_MODEL_SCHEMA")

    def test_quote_hypothetical_even_if_high_probability(self):
        q = quote()
        q["decimal_odds"] = 3.5
        r = check_quote(q)
        self.assertTrue(r["quote_metadata_consistent"])
        self.assertEqual(r["status"], "HOLD")
        self.assertNotIn("ev", r)


if __name__ == "__main__":
    unittest.main()
