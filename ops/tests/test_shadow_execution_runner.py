"""No-network tests for one-pass original A runtime observation and parity."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shadow_forecast
from shadow_execution_runner import run_once
from verify_execution_receipt import verify

NOW = datetime(2026, 10, 9, 4, tzinfo=timezone.utc)
TEAMS = ("A", "B", "C", "D", "E", "F")


def rows():
    history = []
    for i in range(48):
        history.append({
            "date": (NOW - timedelta(days=i+1)).date().isoformat(),
            "home": TEAMS[i%6], "away": TEAMS[(i+1)%6],
            "score_ft": [1+(i%2), int(i%3==0)],
            "status": "FINISHED", "kickoff_utc": None,
            "event_id": f"synthetic-history-{i}",
        })
    history.append({
        "date": "2026-10-10", "home": "A", "away": "B",
        "kickoff_utc": "2026-10-10T12:00:00+00:00",
        "event_id": "synthetic-fixture-id", "score_ft": None,
        "status": "SCHEDULED",
    })
    return history


def getter(*, season, league, clock=None):
    if league == "epl":
        return {"status": "READY_RESEARCH", "source": "TEST_ONLY",
                "matches": rows()}
    return {"status": "HOLD", "source": "TEST_ONLY", "matches": []}


def actual_offline_generate():
    return shadow_forecast.generate(now=NOW, getter=getter,
                                    return_finished=True)


class FixedClock:
    def __init__(self, *values):
        self.values = list(values)
        self.idx = 0

    def __call__(self):
        idx = min(self.idx, len(self.values)-1)
        self.idx += 1
        return self.values[idx]


def times():
    return FixedClock(NOW-timedelta(seconds=1), NOW+timedelta(seconds=1))


class RealOnePassExecutionTests(unittest.TestCase):
    def test_original_A_actually_called_and_exact_prediction_retained(self):
        original = shadow_forecast.predict_league
        expected = original(rows(), "epl", NOW)[0]
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times(), version_sha="a"*40)
        self.assertIs(shadow_forecast.predict_league, original)
        self.assertEqual(result["predictions_count"], 1)
        actual = result["predictions"][0]
        for k in ("p_home", "p_draw", "p_away", "expected_home_goals",
                  "expected_away_goals", "training_observations_sha256"):
            self.assertEqual(actual[k], expected[k])
        self.assertEqual(receipt["original_A_function_calls"], 1)
        self.assertEqual(receipt["successful_original_A_function_calls"], 1)
        self.assertEqual(receipt["valid_original_A_fixture_outputs"], 1)
        self.assertTrue(receipt["model_execution_observed"])
        self.assertEqual(receipt["production_recommendations"], "DISABLED")
        self.assertEqual(receipt["status"], "RESEARCH_ONLY")
        self.assertEqual(receipt["git_commit_sha_unverified_metadata"], "a"*40)
        for k in ("model_invocation_externally_attested",
                  "source_identity_authenticated",
                  "raw_source_capture_authenticated",
                  "result_verified_independently", "odds_available",
                  "verified_positive_ev", "formal_forward_scoring_eligible"):
            self.assertFalse(receipt[k])

    def test_source_failure_means_no_model_call_no_observed_forecast(self):
        def all_fail(**kwargs):
            return {"status":"HOLD","matches":[]}
        result, receipt = run_once(
            generator=lambda: shadow_forecast.generate(
                now=NOW,getter=all_fail,return_finished=True),
            clock=times())
        self.assertEqual(result["predictions_count"], 0)
        self.assertEqual(receipt["original_A_function_calls"], 0)
        self.assertFalse(receipt["model_execution_observed"])
        self.assertEqual(receipt["status"], "HOLD")
        self.assertEqual(receipt["production_recommendations"], "DISABLED")

    def test_generator_exception_restores_original_callable(self):
        original = shadow_forecast.predict_league
        def boom():
            raise RuntimeError("SYNTHETIC_SOURCE_EXCEPTION")
        with self.assertRaises(RuntimeError):
            run_once(generator=boom, clock=times())
        self.assertIs(shadow_forecast.predict_league, original)

    def test_fake_forecast_cannot_claim_unobserved_execution(self):
        def fake():
            o = actual_offline_generate()
            o["predictions"][0]["event_id"] = "invented-after-calculation"
            return o
        with self.assertRaisesRegex(ValueError, "FORECAST_NOT_FROM_THIS_INVOCATION"):
            run_once(generator=fake, clock=times())

    def test_tampered_model_probability_blocked(self):
        def fake():
            o = actual_offline_generate()
            o["predictions"][0]["p_home"] = 0.999
            return o
        with self.assertRaisesRegex(ValueError, "FORECAST_NOT_FROM_THIS_INVOCATION"):
            run_once(generator=fake, clock=times())

    def test_naive_runtime_clock_blocked(self):
        clock = FixedClock(datetime(2026,10,9,4))
        with self.assertRaisesRegex(ValueError, "NAIVE_EXECUTION_CLOCK"):
            run_once(generator=actual_offline_generate, clock=clock)

    def test_time_reversal_blocked(self):
        clock = FixedClock(NOW+timedelta(seconds=1), NOW-timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "UNSAFE_MODEL_EXECUTION_CLOCK"):
            run_once(generator=actual_offline_generate, clock=clock)

    def test_asof_outside_execution_interval_blocked(self):
        clock = FixedClock(NOW+timedelta(seconds=2), NOW+timedelta(seconds=3))
        with self.assertRaisesRegex(ValueError, "ORIGINAL_ASOF_OUTSIDE_ACTUAL_RUN"):
            run_once(generator=actual_offline_generate, clock=clock)

    def test_only_one_existing_source_query_per_league(self):
        calls = []
        def counting(**kwargs):
            calls.append(kwargs["league"])
            return getter(**kwargs)
        _, receipt = run_once(
            generator=lambda: shadow_forecast.generate(
                now=NOW,getter=counting,return_finished=True),
            clock=times())
        self.assertEqual(len(calls), len(shadow_forecast.LEAGUES))
        self.assertEqual(len(set(calls)), len(shadow_forecast.LEAGUES))
        self.assertEqual(receipt["original_A_function_calls"], 1)

    def test_final_publication_check_accepts_same_A_with_AB_research_fields(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        result["predictions"][0]["ab_candidate_p_home"] = 0.15
        result["fixed_low_score_challenger"] = {
            "status": "FORWARD_RESEARCH_CAPTURE_ONLY",
            "production_recommendations": "DISABLED",
        }
        out = verify(result, receipt)
        self.assertEqual(out["status"], "VERIFIED_PROCESS_ONLY")
        self.assertEqual(out["observed_events"], 1)
        self.assertFalse(out["source_authenticated"])
        self.assertFalse(out["betting_eligible"])

    def test_final_publication_rejects_modified_A_probability(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        result["predictions"][0]["p_home"] = 0.9
        with self.assertRaisesRegex(
                ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_final_publication_rejects_wrong_receipt_asof(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        receipt["as_of_utc"] = (NOW+timedelta(seconds=3)).isoformat()
        with self.assertRaisesRegex(ValueError, "UNSAFE_RECEIPT_STATUS_OR_TIME"):
            verify(result, receipt)

    def test_final_publication_rejects_bogus_event_identity(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        result["predictions"][0]["event_id"] = "forged-after-original-model"
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_final_publication_rejects_receipt_claiming_verified_ev(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        receipt["verified_positive_ev"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_RECEIPT_STATUS_OR_TIME"):
            verify(result, receipt)

    def test_final_publication_accepts_no_valid_fixture_with_hold(self):
        def nothing(**kwargs):
            return {"status": "HOLD", "matches": []}
        result, receipt = run_once(
            generator=lambda: shadow_forecast.generate(
                now=NOW,getter=nothing,return_finished=True),
            clock=times())
        out = verify(result, receipt)
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["model_function_called"])
        self.assertEqual(out["observed_events"], 0)

    def test_final_publication_rejects_wrong_model_sha(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        receipt["model_code_sha256"] = "0"*64
        with self.assertRaisesRegex(ValueError, "MODEL_CODE_CHANGED_SINCE_INVOCATION"):
            verify(result, receipt)

    def test_post_generation_home_club_tampering_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["home"] = "Impersonated Home FC"
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_away_club_tampering_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["away"] = "Impersonated Away FC"
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_kickoff_tampering_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["kickoff_utc"] = "2026-10-12T12:00:00+00:00"
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_calibration_flag_promotion_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["calibrated"] = True
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_verified_odds_claim_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["verified_market_odds"] = True
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_training_count_tampering_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["training_games"] += 1000
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_schedule_provenance_tampering_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["schedule_utc_source"] = "claimed-official"
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_post_generation_native_fixture_provenance_injection_is_blocked(self):
        result, receipt = run_once(generator=actual_offline_generate, clock=times())
        result["predictions"][0]["native_fixture_input"] = {
            "status": "UNAUTHENTICATED",
            "provider": "OpenLigaDB",
            "native_ids_from_same_response_as_gateway_fixture": True,
            "source_identity_authenticated": False,
            "source_capture_authenticated": False,
            "eligible_for_model_scoring": False}
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_native_observation_captured_same_run_can_be_retained(self):
        def generator_with_unverified_native():
            result = actual_offline_generate()
            result["predictions"][0]["native_fixture_input"] = {
                "schema": "football-king-native-fixture-input-observation-v1",
                "status": "UNAUTHENTICATED",
                "provider": "OpenLigaDB",
                "match_id": 112,
                "native_ids_from_same_response_as_gateway_fixture": True,
                "source_identity_authenticated": False,
                "source_capture_authenticated": False,
                "raw_input_durably_archived": False,
                "native_ids_used_as_model_features": False,
                "eligible_for_model_scoring": False}
            return result
        result, receipt = run_once(generator=generator_with_unverified_native, clock=times())
        self.assertEqual(verify(result, receipt)["status"], "VERIFIED_PROCESS_ONLY")
        result["predictions"][0]["native_fixture_input"]["match_id"] = 999
        with self.assertRaisesRegex(ValueError, "PUBLISHED_MODEL_EVENT_NOT_OBSERVED"):
            verify(result, receipt)

    def test_daily_original_A_path_rejects_forged_past_date_with_future_kickoff(self):
        fake_history = rows()
        fake_history[0]["kickoff_utc"] = (NOW + timedelta(hours=4)).isoformat()
        def contaminated(*, season, league, clock=None):
            if league == "epl":
                return {"status": "READY_RESEARCH", "source": "TEST_ONLY",
                        "matches": fake_history}
            return {"status": "HOLD", "matches": []}
        result, receipt = run_once(
            generator=lambda: shadow_forecast.generate(
                now=NOW, getter=contaminated, return_finished=True),
            clock=times())
        self.assertEqual(result["predictions_count"], 0)
        self.assertEqual(receipt["original_A_function_calls"], 0)
        self.assertFalse(receipt["model_execution_observed"])
        self.assertEqual(receipt["preflight_rejections"], [{
            "league": "epl", "reason": "HISTORICAL_KICKOFF_TIME_CONFLICT",
            "original_A_invoked": False}])
        self.assertEqual(verify(result, receipt)["status"], "HOLD")

    def test_daily_original_A_rejects_naive_historical_kickoff(self):
        fake_history = rows()
        fake_history[1]["kickoff_utc"] = "2026-10-01T14:30:00"
        def contaminated(*, season, league, clock=None):
            if league == "epl":
                return {"status": "READY_RESEARCH", "source": "TEST_ONLY",
                        "matches": fake_history}
            return {"status": "HOLD", "matches": []}
        result, receipt = run_once(
            generator=lambda: shadow_forecast.generate(
                now=NOW, getter=contaminated, return_finished=True),
            clock=times())
        self.assertEqual(result["predictions_count"], 0)
        self.assertEqual(receipt["original_A_function_calls"], 0)
        self.assertEqual(receipt["preflight_rejections"][0]["reason"],
                         "HISTORICAL_KICKOFF_TIME_CONFLICT")

    def test_retention_path_is_separate_from_existing_shadow(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        self.assertNotIn("execution_receipt", result)
        self.assertIn("_internal_finished_results", result)
        self.assertEqual(receipt["schema"],
                         "football-king-original-A-live-execution-observation-v1")


if __name__ == "__main__":
    unittest.main()
