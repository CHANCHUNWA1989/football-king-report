"""No-network tests for one-pass original A runtime observation and parity."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shadow_forecast
from shadow_execution_runner import run_once

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

    def test_retention_path_is_separate_from_existing_shadow(self):
        result, receipt = run_once(
            generator=actual_offline_generate, clock=times())
        self.assertNotIn("execution_receipt", result)
        self.assertIn("_internal_finished_results", result)
        self.assertEqual(receipt["schema"],
                         "football-king-original-A-live-execution-observation-v1")


if __name__ == "__main__":
    unittest.main()
