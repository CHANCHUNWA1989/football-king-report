"""Synthetic FT records only; immutable REAL forecast bytes from repository.

Never turn the fake [2-0, 1-1] FT observations into actual sports results.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from ops.five_model_pinned_postmatch_audit import (
    PINNED_BLOB_SHA1, PINNED_MANIFEST, RESULT_SCHEMA,
    _git_blob_sha, freeze_preflight, score_pinned,
)


def pinned_bytes():
    return Path(PINNED_MANIFEST).read_bytes()


def fake_two_ft():
    """Made-up test scores, NOT the Nov 21 match results."""
    manifest = json.loads(pinned_bytes())
    observations = []
    for index, fixture in enumerate(manifest["fixtures"]):
        kickoff = datetime.fromisoformat(fixture["kickoff_utc"])
        observations.append({
            "event_id": fixture["event_id"],
            "publishers": [{
                "publisher": "synthetic_test_source_A" if j == 0
                    else "synthetic_test_source_B",
                "source_url": (
                    "https://test-a.invalid/ft/" if j == 0
                    else "https://test-b.invalid/ft/") + str(index),
                "league": "bundesliga",
                "home": fixture["home"], "away": fixture["away"],
                "kickoff_utc": fixture["kickoff_utc"],
                "home_goals": [2, 1][index],
                "away_goals": [0, 1][index],
                "match_status": "FT",
                "observed_utc": (kickoff + timedelta(hours=4)).isoformat(),
            } for j in range(2)],
        })
    return {"schema": RESULT_SCHEMA, "observations": observations}


def serialize(data):
    return json.dumps(data, sort_keys=True, allow_nan=False).encode()


def future_clock():
    return datetime(2026, 11, 23, 12, tzinfo=timezone.utc)


class PinnedFiveModelAuditTests(unittest.TestCase):
    def test_original_git_blob_is_frozen_and_pregame(self):
        original = pinned_bytes()
        self.assertEqual(_git_blob_sha(original), PINNED_BLOB_SHA1)
        review = freeze_preflight(original)
        self.assertTrue(review["preflight_passed"], review)
        self.assertEqual(review["scored_matches"], 0)
        self.assertEqual(len(review["fixture_ids"]), 2)
        self.assertFalse(review["positive_ev_verified"])
        self.assertEqual(review["production_recommendations"], "DISABLED")
        self.assertFalse(review["forecast_independent_timestamp_attested"])

    def test_edited_prognosis_or_future_local_time_rejected(self):
        data = pinned_bytes()
        changed = data.replace(b"0.800144", b"0.900144", 1)
        self.assertNotEqual(changed, data)
        result = freeze_preflight(changed)
        self.assertEqual(result["reason"], "PINNED_FORECAST_GIT_BLOB_CHANGED")
        self.assertFalse(result["model_promoted"])
        data = json.loads(pinned_bytes())
        data["fixtures"][0]["local_fifth_finished_utc"] = "2026-11-22T23:30:00Z"
        self.assertEqual(freeze_preflight(serialize(data))["reason"],
                         "PINNED_FORECAST_GIT_BLOB_CHANGED")

    def test_synthetic_two_source_full_time_scores_five_models(self):
        results = fake_two_ft()
        original = deepcopy(results)
        report = score_pinned(pinned_bytes(), serialize(results), now=future_clock())
        self.assertEqual(original, results)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"],
                         "TWO_SOURCE_METADATA_CONCORDANT_RESEARCH_SCORE_NOT_CERTIFIED")
        self.assertEqual(report["scored_matches"], 2)
        self.assertTrue(report["preflight_passed"])
        self.assertTrue(report["result_source_metadata_agreement"])
        self.assertEqual(len(report["original_five_model_1x2_scores"]), 5)
        for model, metrics in report["original_five_model_1x2_scores"].items():
            self.assertEqual(metrics["n"], 2)
            self.assertIn(metrics["direction_hits"], (0, 1, 2))
            self.assertGreaterEqual(metrics["mean_brier"], 0)
            self.assertGreaterEqual(metrics["mean_logloss"], 0)
        self.assertEqual(set(report["pinned_two_model_market_grade_scores"]),
                         {"bivariate", "dynamic"})
        for markets in report["pinned_two_model_market_grade_scores"].values():
            self.assertEqual(set(markets), {"OVER_2.75", "HOME_AH_-0.25"})
            self.assertTrue(all(entry["n"] == 2 for entry in markets.values()))
        self.assertFalse(report["statistical_superiority_proven"])
        self.assertFalse(report["confidence_intervals_valid_for_two_matches"])
        self.assertFalse(report["two_publisher_source_independence_certified"])
        self.assertFalse(report["bookmaker_quotes_or_ev_verified"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_before_first_result_mature_never_scores(self):
        results = fake_two_ft()
        kickoff = datetime.fromisoformat(
            json.loads(pinned_bytes())["fixtures"][0]["kickoff_utc"])
        result = score_pinned(pinned_bytes(), serialize(results),
                              now=kickoff + timedelta(minutes=60))
        self.assertEqual(result["reason"], "MATCH_NOT_MATURE_FOR_FULL_TIME_REVIEW")
        self.assertNotIn("original_five_model_1x2_scores", result)

    def test_missing_or_duplicate_result_blocks_all_models(self):
        results = fake_two_ft()
        results["observations"].pop()
        blocked = score_pinned(pinned_bytes(), serialize(results), now=future_clock())
        self.assertEqual(blocked["reason"], "REQUIRES_BOTH_PINNED_FT_FIXTURES")
        results = fake_two_ft()
        results["observations"][1]["event_id"] = results["observations"][0]["event_id"]
        blocked = score_pinned(pinned_bytes(), serialize(results), now=future_clock())
        self.assertEqual(blocked["reason"], "DUPLICATE_UNKNOWN_OR_MISSING_FIXTURE")
        self.assertNotIn("original_five_model_1x2_scores", blocked)

    def test_mismatch_tampered_provider_or_shared_domain_blocks(self):
        for modification in ("score_conflict", "identity_drift", "duplicate_host",
                             "not_final", "source_seen_before_ft", "future_source"):
            results = fake_two_ft()
            second = results["observations"][0]["publishers"][1]
            if modification == "score_conflict":
                second["away_goals"] = 5
            elif modification == "identity_drift":
                second["away"] = "Different Club"
            elif modification == "duplicate_host":
                second["source_url"] = "https://test-a.invalid/second"
            elif modification == "not_final":
                second["match_status"] = "LIVE"
            elif modification == "source_seen_before_ft":
                second["observed_utc"] = "2026-11-20T19:30:00Z"
            else:
                second["observed_utc"] = "2026-12-01T00:00:00Z"
            with self.subTest(modification=modification):
                report = score_pinned(pinned_bytes(), serialize(results),
                                      now=future_clock())
                self.assertEqual(report["status"], "HOLD")
                self.assertNotIn("original_five_model_1x2_scores", report)
                self.assertFalse(report["positive_ev_verified"])

    def test_duplicate_json_keys_and_nan_rejected(self):
        body = serialize(fake_two_ft())
        bad = body.replace(b'"schema":', b'"schema": "spoof", "schema":', 1)
        self.assertEqual(score_pinned(pinned_bytes(), bad, now=future_clock())[
            "reason"], "INVALID_RESULT_EVIDENCE_OR_TIMESTAMPS")
        bad2 = body.replace(b'"home_goals": 2', b'"home_goals": NaN', 1)
        self.assertEqual(score_pinned(pinned_bytes(), bad2, now=future_clock())[
            "reason"], "INVALID_RESULT_EVIDENCE_OR_TIMESTAMPS")


if __name__ == "__main__":
    unittest.main()
