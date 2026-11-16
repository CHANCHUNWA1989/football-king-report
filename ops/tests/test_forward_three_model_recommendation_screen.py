"""Strict synthetic adversarial tests. No claims of real EV or new score."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from ops.forward_three_model_recommendation_screen import (
    SOURCE_SCHEMA, screen, MAX_SOURCE_AGE_DAYS,
)

UTC = timezone.utc
CAPTURE = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
KICKOFF = "2026-11-16T19:45:00+00:00"


def source():
    return {
        "schema": SOURCE_SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "certified_prospective_samples": 0,
        "historical_result_publication_times_verified": False,
        "genuine_source_authenticity_verified": False,
        "original_a_is_adapted_club_algorithm_not_native_uefa_producer": True,
        "dataset_fetched_utc": CAPTURE.isoformat(),
        "dataset_max_result_date": "2026-11-13",
        "observations": [{
            "fixture": "future-neutral-reference",
            "home": "synthetic-home", "away": "synthetic-away",
            "kickoff_utc": KICKOFF,
            "status": "UNVERIFIED_PREMATCH_PROBABILITIES",
            "a_computed_utc_unattested": (
                CAPTURE + timedelta(seconds=1)).isoformat(),
            "models_completed_utc_unattested": (
                CAPTURE + timedelta(seconds=4)).isoformat(),
            "no_uefa_native_event_id_claimed": True,
            "original_a_algorithm_1x2": [0.54, 0.25, 0.21],
            "real_penaltyblog_poisson_1x2": [0.55, 0.24, 0.21],
            "real_penaltyblog_dixon_coles_1x2": [0.53, 0.23, 0.24],
        }],
    }


class ForwardScreenTests(unittest.TestCase):
    def check(self, data=None, *, now=CAPTURE + timedelta(seconds=5)):
        result = screen(source() if data is None else data, observed_at=now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["model_promoted"])
        self.assertFalse(result["source_publisher_authenticated"])
        self.assertFalse(result["historical_results_independently_timestamped"])
        self.assertFalse(result["bookmaker_price_independently_executable"])
        self.assertEqual(result["certified_prospective_samples"], 0)
        return result

    def reject(self, reason, data=None, *, now=CAPTURE+timedelta(seconds=5)):
        result = self.check(data, now=now)
        self.assertIn(reason, result["fixtures"][0]["research_blockers"])
        self.assertEqual(result["unverified_candidate_count"], 0)
        self.assertEqual(result["rejected_fixture_count"], 1)

    def test_allow_candidate_label_only_never_wager(self):
        r=self.check()
        self.assertEqual(r["unverified_candidate_count"],1)
        self.assertEqual(r["fixtures"][0]["consensus_direction"],"HOME")
        self.assertTrue(r["only_forward_filter_no_lookahead"])
        self.assertTrue(r["not_a_proven_backtest_uplift"])

    def test_reject_old_source_40_days(self):
        d=source();d["dataset_max_result_date"]="2026-10-06"
        self.reject("SOURCE_HISTORY_STALE_OR_FROM_FUTURE", d)

    def test_source_exact_14_days_is_research_only(self):
        d=source();d["dataset_max_result_date"]="2026-11-01"
        self.assertEqual(self.check(d)["unverified_candidate_count"],1)

    def test_source_15_days_automatically_rejected(self):
        d=source();d["dataset_max_result_date"]="2026-10-31"
        self.reject("SOURCE_HISTORY_STALE_OR_FROM_FUTURE",d)

    def test_future_source_record_claim_is_rejected(self):
        d=source();d["dataset_max_result_date"]="2026-11-16"
        self.reject("SOURCE_HISTORY_STALE_OR_FROM_FUTURE",d)

    def test_reject_exactly_ten_minutes_before_start_if_already_assessed(self):
        self.reject("ASSESSMENT_NOT_PREMATCH",
                    now=datetime(2026,11,16,19,35,tzinfo=UTC))

    def test_reject_assessment_after_result(self):
        self.reject("ASSESSMENT_NOT_PREMATCH",
                    now=datetime(2026,11,17,14,0,tzinfo=UTC))

    def test_source_captured_after_kickoff(self):
        d=source()
        d["observations"][0]["kickoff_utc"]="2026-11-15T12:04:00+00:00"
        self.reject("SOURCE_NOT_PREMATCH",d)

    def test_source_clock_future_of_model_clock(self):
        d=source()
        d["observations"][0]["a_computed_utc_unattested"]=(
            CAPTURE-timedelta(seconds=1)).isoformat()
        self.reject("MODEL_CLOCK_NOT_BEFORE_KICKOFF",d)

    def test_local_model_end_not_before_kickoff(self):
        d=source()
        d["observations"][0]["models_completed_utc_unattested"]=(
            datetime(2026,11,16,19,35,tzinfo=UTC)).isoformat()
        self.reject("MODEL_CLOCK_NOT_BEFORE_KICKOFF",d)

    def test_local_model_end_future_vs_audit_now(self):
        d=source()
        d["observations"][0]["models_completed_utc_unattested"]=(
            CAPTURE+timedelta(minutes=3)).isoformat()
        self.reject("FORECAST_COMPLETION_IN_FUTURE",d)

    def test_original_a_away_vs_challenger_draw_blocks(self):
        d=source()
        d["observations"][0]["original_a_algorithm_1x2"]=[0.3,0.2,0.5]
        d["observations"][0]["real_penaltyblog_poisson_1x2"]=[0.32,0.4,0.28]
        d["observations"][0]["real_penaltyblog_dixon_coles_1x2"]=[0.33,0.39,0.28]
        self.reject("MODEL_TOP_DIRECTION_CONFLICT_OR_TIE",d)

    def test_original_a_away_vs_challenger_home_blocks(self):
        d=source()
        d["observations"][0]["original_a_algorithm_1x2"]=[0.24,0.18,0.58]
        self.reject("MODEL_TOP_DIRECTION_CONFLICT_OR_TIE",d)

    def test_all_model_draw_consensus_research_only(self):
        d=source()
        for key in ("original_a_algorithm_1x2",
                    "real_penaltyblog_poisson_1x2",
                    "real_penaltyblog_dixon_coles_1x2"):
            d["observations"][0][key]=[.3,.4,.3]
        r=self.check(d)
        self.assertEqual(r["fixtures"][0]["consensus_direction"],"DRAW")

    def test_all_away_consensus_research_only(self):
        d=source()
        for key in ("original_a_algorithm_1x2",
                    "real_penaltyblog_poisson_1x2",
                    "real_penaltyblog_dixon_coles_1x2"):
            d["observations"][0][key]=[.2,.3,.5]
        r=self.check(d)
        self.assertEqual(r["fixtures"][0]["consensus_direction"],"AWAY")

    def test_true_tie_is_rejected(self):
        d=source()
        d["observations"][0]["original_a_algorithm_1x2"]=[.4,.4,.2]
        self.reject("MODEL_TOP_DIRECTION_CONFLICT_OR_TIE",d)

    def test_all_agree_but_probability_spread_above_20pp_rejected(self):
        d=source()
        d["observations"][0]["original_a_algorithm_1x2"]=[.79,.11,.10]
        d["observations"][0]["real_penaltyblog_poisson_1x2"]=[.50,.25,.25]
        self.reject("TOP_PROBABILITY_SPREAD_ABOVE_20PP",d)

    def test_invalid_nonfinite_or_wrong_probability_sum_blocks_entire_snapshot(self):
        for v in ([float("nan"),0.3,0.7],[0.8,0.5,-0.3],
                  [0.8,0.1,0.2],[True,0.7,0.3],[.3,.7]):
            with self.subTest(v=v):
                d=source()
                d["observations"][0]["original_a_algorithm_1x2"]=v
                r=self.check(d)
                self.assertNotIn("fixtures",r)
                self.assertEqual(r["reason"],"INVALID_UNVERIFIED_INPUT_OR_CLOCK")

    def test_unfinished_optional_model_is_not_assumed_successful(self):
        d=source();d["observations"][0]["status"]="HOLD"
        self.reject("THREE_MODELS_NOT_COMPLETED",d)

    def test_no_native_id_authenticity_is_not_invented(self):
        d=source();d["observations"][0]["no_uefa_native_event_id_claimed"]=False
        self.reject("INVALID_NATIVE_IDENTITY_DISCLOSURE",d)

    def test_duplicate_event_rejects_entire_cohort(self):
        d=source();d["observations"].append(copy.deepcopy(d["observations"][0]))
        r=self.check(d)
        self.assertNotIn("fixtures",r)
        self.assertEqual(r["reason"],"INVALID_UNVERIFIED_INPUT_OR_CLOCK")

    def test_same_teams_in_single_event_rejected(self):
        d=source();d["observations"][0]["away"]="synthetic-home"
        r=self.check(d)
        self.assertEqual(r["reason"],"INVALID_UNVERIFIED_INPUT_OR_CLOCK")

    def test_missing_report_fails_closed(self):
        r=self.check({"status":"HOLD"})
        self.assertEqual(r["reason"],"SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")

    def test_report_with_false_eligibility_claim_blocked(self):
        d=source();d["positive_ev_verified"]=True
        r=self.check(d)
        self.assertEqual(r["reason"],"SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")

    def test_report_with_pretended_prospective_sample_blocked(self):
        d=source();d["certified_prospective_samples"]=1
        r=self.check(d)
        self.assertEqual(r["reason"],"SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")

    def test_report_with_pretended_authenticated_source_blocked(self):
        d=source();d["genuine_source_authenticity_verified"]=True
        r=self.check(d)
        self.assertEqual(r["reason"],"SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")

    def test_report_with_pretended_result_clock_authentication_blocked(self):
        d=source();d["historical_result_publication_times_verified"]=True
        r=self.check(d)
        self.assertEqual(r["reason"],"SOURCE_FORECAST_NOT_TRUSTED_FOR_RESEARCH_SCREEN")

    def test_frozen_nov15_actual_history_remains_rejected_even_before_kickoff(self):
        # Trace this input to PR #458's frozen actual Nov15 cohort; unlike
        # adversarial examples, these three probability vectors were observed
        # in the REAL run #43711801983 and remain UNSIGNED.
        d=source()
        d["dataset_max_result_date"]="2026-10-06"
        d["dataset_fetched_utc"]="2026-11-15T12:03:03.897677+00:00"
        d["observations"][0].update({
            "fixture":"belarus-albania", "home":"Belarus", "away":"Albania",
            "kickoff_utc":"2026-11-15T17:00:00+00:00",
            "a_computed_utc_unattested":"2026-11-15T12:03:04.090579+00:00",
            "models_completed_utc_unattested":"2026-11-15T12:03:07.090801+00:00",
            "original_a_algorithm_1x2":[.3019987,.2681697,.4298316],
            "real_penaltyblog_poisson_1x2":[.3327121768411414,.3756706013623402,.2916172217965185],
            "real_penaltyblog_dixon_coles_1x2":[.32489835329940764,.39076341907797246,.28433822762262007],
        })
        r=self.check(d,now=datetime(2026,11,15,12,3,8,tzinfo=UTC))
        self.assertEqual(r["rejected_fixture_count"],1)
        self.assertIn("SOURCE_HISTORY_STALE_OR_FROM_FUTURE",
                      r["fixtures"][0]["research_blockers"])
        self.assertIn("MODEL_TOP_DIRECTION_CONFLICT_OR_TIE",
                      r["fixtures"][0]["research_blockers"])
        self.assertFalse(r["model_promoted"])


if __name__ == "__main__":
    unittest.main()
