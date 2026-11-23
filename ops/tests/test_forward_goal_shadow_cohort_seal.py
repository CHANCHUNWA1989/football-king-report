import copy
from datetime import datetime, timezone
import hashlib
import json
import unittest

from ops.forward_goal_shadow_cohort_seal import (
    SCHEMA, build, verify, _canonical,
)

NOW = datetime(2026, 11, 16, 15, 30, tzinfo=timezone.utc)
REV = "e466196956a0780776bc90ef1168f6c462024c3e"


def input_rows():
    return {
        "schema": SCHEMA,
        "production_recommendations": "DISABLED",
        "source": {
            "namespace": "openligadb",
            "league": "bundesliga",
            "source_response_sha256": "a" * 64,
            "source_received_utc": "2026-11-16T15:20:00Z",
            "source_capture_id": "source-run-37",
        },
        "training": {
            "league": "bundesliga",
            "training_source_sha256": "b" * 64,
            "training_cutoff_utc": "2026-11-15T23:00:00Z",
            "training_match_count": 120,
            "over25_frequency": 0.53,
            "btts_frequency": 0.56,
        },
        "fixtures": [
            {"fixture_id": "openligadb:10001", "home_team_id": "100",
             "away_team_id": "101", "kickoff_utc": "2026-11-21T12:30:00Z"},
            {"fixture_id": "openligadb:10002", "home_team_id": "102",
             "away_team_id": "103", "kickoff_utc": "2026-11-21T14:30:00Z"},
        ],
        "forecasts": [
            {"fixture_id": "openligadb:10001",
             "model_revision_sha": REV,
             "computed_utc": "2026-11-16T15:25:00Z",
             "expected_home_goals": 1.7,
             "expected_away_goals": 1.2},
        ],
    }


class ForwardGoalCohortSealTests(unittest.TestCase):
    def test_freezes_every_fixture_including_missing_forecast(self):
        records = input_rows()
        saved = copy.deepcopy(records)
        r = build(records, now=NOW)
        self.assertTrue(verify(r))
        self.assertEqual(records, saved)
        self.assertEqual(r["payload"]["source_fixture_universe_count"], 2)
        self.assertEqual(r["payload"]["prematch_forecasts_present"], 1)
        self.assertEqual(r["payload"]["missing_forecasts_included_as_holds"], 1)
        self.assertEqual(r["payload"]["fixtures"][1]["state"], "HOLD_NO_PREMATCH_MODEL")
        self.assertEqual(r["payload"]["certified_prospective_samples"], 0)
        self.assertEqual(r["payload"]["production_recommendations"], "DISABLED")
        self.assertFalse(r["payload"]["eligible_for_model_promotion"])
        self.assertFalse(r["payload"]["actual_bookmaker_quotes_verified"])

    def test_calculates_fixed_training_only_probabilities(self):
        a = build(input_rows(), now=NOW)
        target = a["payload"]["fixtures"][0]
        self.assertGreater(target["over25"]["exploratory_75_25_blend"], 0)
        self.assertAlmostEqual(
            target["over25"]["exploratory_75_25_blend"],
            .75 * target["over25"]["original"] + .25 * .53)
        self.assertAlmostEqual(
            target["btts"]["exploratory_75_25_blend"],
            .75 * target["btts"]["original"] + .25 * .56)
        self.assertIsNone(a["payload"]["fixtures"][1]["over25"])

    def test_reject_started_or_near_kickoff_even_if_model_earlier(self):
        d = input_rows()
        d["fixtures"][1]["kickoff_utc"] = "2026-11-16T15:35:00Z"
        with self.assertRaisesRegex(ValueError, "LATE_OR_STARTED_FIXTURE"):
            build(d, now=NOW)
        d["fixtures"][1]["kickoff_utc"] = "2026-11-16T15:25:00Z"
        with self.assertRaisesRegex(ValueError, "LATE_OR_STARTED_FIXTURE"):
            build(d, now=NOW)

    def test_reject_post_source_future_and_stale_clock(self):
        d = input_rows()
        d["source"]["source_received_utc"] = "2026-11-16T15:31:00Z"
        with self.assertRaisesRegex(ValueError, "SOURCE_CAPTURE_STALE_OR_FUTURE"):
            build(d, now=NOW)
        d["source"]["source_received_utc"] = "2026-11-16T14:00:00Z"
        with self.assertRaisesRegex(ValueError, "SOURCE_CAPTURE_STALE_OR_FUTURE"):
            build(d, now=NOW)
        d = input_rows()
        d["forecasts"][0]["computed_utc"] = "2026-11-16T15:10:00Z"
        with self.assertRaisesRegex(ValueError, "FORECAST_NOT_FRESH_PREMATCH"):
            build(d, now=NOW)
        d["forecasts"][0]["computed_utc"] = "2026-11-16T15:32:00Z"
        with self.assertRaisesRegex(ValueError, "FORECAST_NOT_FRESH_PREMATCH"):
            build(d, now=NOW)

    def test_reject_training_prior_after_source_or_boolean(self):
        d = input_rows()
        d["training"]["training_cutoff_utc"] = "2026-11-16T15:20:00Z"
        with self.assertRaisesRegex(ValueError, "TRAINING_CUTOFF_NOT_BEFORE_SOURCE"):
            build(d, now=NOW)
        d = input_rows()
        d["training"]["over25_frequency"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_TRAINING_PRIOR"):
            build(d, now=NOW)
        d = input_rows()
        d["training"]["training_match_count"] = True
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_TRAINING"):
            build(d, now=NOW)

    def test_reject_duplicate_or_injected_forecast(self):
        d = input_rows()
        d["forecasts"].append(copy.deepcopy(d["forecasts"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_UNLISTED_FORECAST"):
            build(d, now=NOW)
        d = input_rows()
        d["forecasts"][0]["fixture_id"] = "openligadb:99999"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_UNLISTED_FORECAST"):
            build(d, now=NOW)
        d = input_rows()
        d["fixtures"].append(copy.deepcopy(d["fixtures"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE_OR_TEAM_ID"):
            build(d, now=NOW)

    def test_reject_nonfinite_score_injection_odds_or_results(self):
        d = input_rows()
        d["forecasts"][0]["expected_home_goals"] = float("nan")
        with self.assertRaisesRegex(ValueError, "INVALID_ORIGINAL_GOAL_RATES"):
            build(d, now=NOW)
        d = input_rows()
        d["forecasts"][0]["expected_home_goals"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_ORIGINAL_GOAL_RATES"):
            build(d, now=NOW)
        d = input_rows()
        d["forecasts"][0]["final_score"] = [2, 1]
        with self.assertRaisesRegex(ValueError, "INVALID_FORECAST_CONTRACT"):
            build(d, now=NOW)
        d = input_rows()
        d["forecasts"][0]["bookmaker_odds"] = 2.05
        with self.assertRaisesRegex(ValueError, "INVALID_FORECAST_CONTRACT"):
            build(d, now=NOW)

    def test_reject_fixture_identity_conflict(self):
        d = input_rows()
        d["fixtures"][0]["fixture_id"] = "otherprovider:10001"
        with self.assertRaisesRegex(ValueError, "FIXTURE_SOURCE_ID_MISMATCH"):
            build(d, now=NOW)
        d = input_rows()
        d["fixtures"][0]["away_team_id"] = "100"
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE_OR_TEAM_ID"):
            build(d, now=NOW)
        d = input_rows()
        d["training"]["league"] = "epl"
        with self.assertRaisesRegex(ValueError, "TRAINING_LEAGUE_MISMATCH"):
            build(d, now=NOW)

    def test_sha_detects_mutation_after_freeze(self):
        sealed = build(input_rows(), now=NOW)
        sealed["payload"]["fixtures"][0]["over25"]["original"] = 0.999
        with self.assertRaisesRegex(ValueError, "COHORT_ENVELOPE_TAMPERED"):
            verify(sealed)

    def test_reject_mixed_model_revisions(self):
        d = input_rows()
        d["forecasts"].append({
            "fixture_id": "openligadb:10002", "model_revision_sha": "c"*40,
            "computed_utc": "2026-11-16T15:27:00Z",
            "expected_home_goals": 1.2, "expected_away_goals": 1.0,
        })
        with self.assertRaisesRegex(ValueError, "MIXED_MODEL_REVISIONS"):
            build(d, now=NOW)

    def test_excluded_lookahead_or_false_certification_claims(self):
        d = input_rows()
        d["independently_attested"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_INPUT_CONTRACT"):
            build(d, now=NOW)
        d = input_rows()
        d["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "UNSAFE_RECOMMENDATION_CONTRACT"):
            build(d, now=NOW)


if __name__ == "__main__":
    unittest.main()
