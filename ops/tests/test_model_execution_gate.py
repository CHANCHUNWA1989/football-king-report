"""Execution truth contract: never label unsupported/absent model as run."""
from datetime import datetime, timedelta, timezone
import copy
from unittest.mock import patch
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_execution_gate import execute, SCHEMA
from shadow_forecast import predict_league

HKT = ZoneInfo("Asia/Hong_Kong")
NOW = datetime(2026, 11, 21, 9, tzinfo=timezone.utc)
TEAMS = ("A", "B", "C", "D", "E", "F")


def rows():
    events = []
    for i in range(72):
        day = (NOW - timedelta(days=i+1)).astimezone(HKT).date().isoformat()
        events.append({
            "event_id": "synthetic-historical-id-" + str(i),
            "date": day,
            "home": TEAMS[i % 6],
            "away": TEAMS[(i + 1) % 6],
            "status": "FINISHED",
            "score_ft": [1 + (i % 3 == 0), int(i % 4 == 0)],
            "kickoff_utc": None,
        })
    kickoff = NOW + timedelta(days=2)
    events.append({
        "event_id": "synthetic-fixture-original-A",
        "date": kickoff.astimezone(HKT).date().isoformat(),
        "home": "A",
        "away": "B",
        "status": "SCHEDULED",
        "score_ft": None,
        "kickoff_utc": kickoff.isoformat(),
    })
    return events


def run(data=None, league="epl", event="synthetic-fixture-original-A",
        now=NOW):
    return execute(rows() if data is None else data,
                   league=league, event_id=event, now=now)


class ActualModelExecutionContractTests(unittest.TestCase):
    def test_supported_fixture_calls_original_real_code(self):
        data = rows()
        original = predict_league(data, "epl", NOW)[0]
        output = run(data=data)
        self.assertEqual(output["schema"], SCHEMA)
        self.assertTrue(output["model_executed"])
        self.assertEqual(output["status"], "EXECUTED_RESEARCH_ONLY")
        self.assertEqual(output["model_probabilities"],
                         [original[k] for k in
                          ("p_home", "p_draw", "p_away")])
        self.assertEqual(output["model_name"], original["model"])
        self.assertEqual(output["training_observations_sha256"],
                         original["training_observations_sha256"])
        self.assertEqual(len(output["execution_source_sha256"]), 64)
        self.assertEqual(output["model_source_ref"],
                         "ops/shadow_forecast.py:predict_league")
        self.assertEqual(output["production_recommendations"], "DISABLED")
        self.assertFalse(output["verified_market_prices"])
        self.assertFalse(output["source_fixture_identity_verified"])
        self.assertFalse(output["verified_positive_ev"])

    def test_brisbane_a_league_explicitly_not_modelled(self):
        output = run(data=None, league="aleague",
                     event="brisbane-roar-sydneyfc-2026-11-21")
        self.assertEqual(output["status"], "HOLD")
        self.assertEqual(output["reason"], "MODEL_UNAVAILABLE_UNSUPPORTED_LEAGUE")
        self.assertFalse(output["model_executed"])
        self.assertIsNone(output["model_probabilities"])
        self.assertIsNone(output["expected_goals"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_missing_input_fails_closed_without_claimed_run(self):
        output = run(data=[], league="epl")
        self.assertEqual(output["reason"], "MISSING_OR_INVALID_FIXTURE_HISTORY_INPUT")
        self.assertFalse(output["model_executed"])

    def test_no_original_source_event_id_blocks(self):
        output = run(event="")
        self.assertEqual(output["reason"], "MISSING_OR_INVALID_SOURCE_EVENT_ID")

    def test_unknown_exact_event_id_blocks(self):
        output = run(event="nonexistent:fixture")
        self.assertEqual(output["reason"],
                         "DUPLICATE_OR_UNMATCHED_SOURCE_EVENT_ID")

    def test_double_event_id_blocks_fuzzy_reassignment(self):
        old = rows()
        old.append(copy.deepcopy(old[-1]))
        result = run(old)
        self.assertEqual(result["reason"],
                         "DUPLICATE_OR_UNMATCHED_SOURCE_EVENT_ID")

    def test_result_in_candidate_blocks_before_prediction(self):
        old = rows()
        old[-1]["score_ft"] = [3, 0]
        result = run(old)
        self.assertEqual(result["reason"], "NO_CLEAN_PREMATCH_SOURCE_FIXTURE")

    def test_past_kickoff_does_not_get_replay_forecast(self):
        old = rows()
        ko = NOW - timedelta(hours=1)
        old[-1]["date"] = ko.astimezone(HKT).date().isoformat()
        old[-1]["kickoff_utc"] = ko.isoformat()
        self.assertEqual(run(old)["reason"],
                         "NO_ELIGIBLE_ORIGINAL_MODEL_FORECAST")

    def test_missing_sufficient_historical_games_is_hold(self):
        old = rows()[:8] + [rows()[-1]]
        self.assertEqual(run(old)["reason"],
                         "NO_ELIGIBLE_ORIGINAL_MODEL_FORECAST")

    def test_naive_analysis_time_blocks(self):
        self.assertEqual(run(now=datetime(2026,11,21,9))["reason"],
                         "INVALID_OR_NAIVE_RUN_CLOCK")

    def test_malformed_data_without_model_is_not_analysis(self):
        self.assertEqual(run(data=[{"some":"statistics"}])["reason"],
                         "DUPLICATE_OR_UNMATCHED_SOURCE_EVENT_ID")

    def test_same_input_order_permutation_is_identical_model_output(self):
        old = rows()
        transformed = list(reversed(old[:-1])) + old[-1:]
        a, b = run(old), run(transformed)
        self.assertEqual(a["model_probabilities"], b["model_probabilities"])
        self.assertEqual(a["training_observations_sha256"],
                         b["training_observations_sha256"])

    def test_model_snapshot_is_not_third_party_attestation(self):
        result = run()
        self.assertTrue(result["model_executed"])
        for field in (
            "provider_capture_authenticated",
            "execution_time_externally_attested",
            "independent_result_verified",
            "model_calibrated",
            "true_live_match_model_validated",
            "betting_eligible",
        ):
            self.assertFalse(result[field], field)

    def test_forged_past_result_with_future_kickoff_is_rejected(self):
        old = rows()
        old[0]["kickoff_utc"] = (NOW + timedelta(hours=2)).isoformat()
        out = run(old)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["reason"], "HISTORICAL_KICKOFF_TIME_CONFLICT")
        self.assertFalse(out["model_executed"])
        self.assertIsNone(out["model_probabilities"])

    def test_past_result_with_mismatched_hong_kong_day_is_rejected(self):
        old = rows()
        old[1]["kickoff_utc"] = (NOW - timedelta(hours=30)).isoformat()
        out = run(old)
        self.assertEqual(out["reason"], "HISTORICAL_KICKOFF_TIME_CONFLICT")
        self.assertFalse(out["model_executed"])

    def test_historical_kickoff_without_timezone_is_rejected(self):
        old = rows()
        old[2]["kickoff_utc"] = "2026-11-01T11:00:00"
        out = run(old)
        self.assertEqual(out["reason"], "HISTORICAL_KICKOFF_TIME_CONFLICT")
        self.assertFalse(out["model_executed"])

    def test_history_with_no_kickoff_remains_unattested_research(self):
        out = run()
        self.assertTrue(out["model_executed"])
        self.assertFalse(out["historical_kickoff_times_complete"])
        self.assertFalse(out["source_fixture_identity_verified"])

    def test_invalid_input_encoding_must_block_before_model_call(self):
        # Ignored NaN metadata would not interrupt original A but must not
        # produce a claim that no model ran *after* invoking A.
        old = rows()
        old[0]["ignored_untrusted_metadata"] = float("nan")
        with patch("model_execution_gate.predict_league",
                   side_effect=AssertionError("MODEL_MUST_NOT_RUN")) as model:
            out = run(old)
            model.assert_not_called()
        self.assertEqual(out["reason"], "INVALID_MODEL_INPUT_ENCODING")
        self.assertFalse(out["model_executed"])
        self.assertIsNone(out["model_probabilities"])

    def test_unserializable_input_must_block_before_model_call(self):
        old = rows()
        old[1]["ignored_untrusted_metadata"] = object()
        with patch("model_execution_gate.predict_league",
                   side_effect=AssertionError("MODEL_MUST_NOT_RUN")) as model:
            out = run(old)
            model.assert_not_called()
        self.assertEqual(out["reason"], "INVALID_MODEL_INPUT_ENCODING")
        self.assertFalse(out["model_executed"])

    def test_no_input_ever_enables_production(self):
        for x in (
            run(), run(league="aleague"), run(data=[]),
            run(event="bad"), run(now=datetime(2026,11,21))
        ):
            self.assertEqual(x["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
