"""Synthetic metadata only: J1 pilot must never spend credits or certify EV."""
import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from j1_shadow_zero_credit_preflight import (
    MAX_DIAGNOSTIC_AGE, SCHEMA, assess, main,
)


STAMP = datetime(2026, 11, 22, 8, 43, 24, tzinfo=timezone.utc)


def _source(name, configured, status, reason):
    return {
        "provider": name, "configured": configured, "status": status,
        "reason": reason, "requests_attempted": 0 if not configured else 1,
        "upcoming_events": 0,
        "fresh_3way_event_count": 0, "fresh_spread_event_count": 0,
        "fresh_totals_event_count": 0, "free_stale_quote_rejects": 0,
        "market_quotes_are_not_executable": True,
        "independently_calibrated_j1_model": False,
        "production_recommendations": "DISABLED",
    }


def sample():
    prop = _source("propline", True, "RESEARCH_ONLY",
                   "FRESH_PREMATCH_RESEARCH_METADATA_ONLY")
    prop.update({
        "upcoming_events": 7, "fresh_3way_event_count": 7,
        "fresh_spread_event_count": 7, "fresh_totals_event_count": 7,
        "provider_daily_remaining": 999,
    })
    rundown = _source("therundown", False, "NOT_CONFIGURED",
                      "PRIVATE_FREE_KEY_NOT_CONFIGURED")
    odds = _source("the_odds_api_j1", True, "HOLD",
                   "PRESERVE_EXISTING_SIX_LEAGUE_FREE_CREDITS")
    odds["quota_remaining"] = 141
    return {
        "schema": "football-king-japan-free-market-research-v1",
        "collected_utc": STAMP.isoformat(),
        "status": "RESEARCH_ONLY",
        "j1_free_prematch_sources": [prop, rundown, odds],
        "cross_feed_consistency_observation": {
            "same_fixture_two_api_observations": 0,
            "median_abs_home_probability_delta": None,
            "api_provider_count_is_not_independent_bookmaker_count": True,
            "independent_venue_quote_verified": False,
        },
        "the_odds_api_european_six_league_market_is_untouched": True,
        "j1_fixtures_not_independently_verified": True,
        "j1_model_remains_uncalibrated": True,
        "j1_2026_27_outcomes_not_proven": True,
        "realtime_inplay_quotes_confirmed": False,
        "free_tier_closing_lines_available": False,
        "raw_bookmaker_prices_or_names_redistributed": False,
        "estimated_roi": None,
        "bet_recommendation_count": 0,
        "production_recommendations": "DISABLED",
        "no_secret_values_logged_or_persisted": True,
    }


class J1ZeroCreditShadowPreflightTests(unittest.TestCase):
    def audit(self, doc=None, age=timedelta(minutes=20)):
        return assess(sample() if doc is None else doc, now=STAMP + age)

    def test_cached_status_reports_seven_only_as_metadata(self):
        r = self.audit()
        self.assertEqual(r["schema"], SCHEMA)
        self.assertEqual(r["sport_key"], "soccer_japan_j_league")
        self.assertEqual(r["market_scope"], "PREMATCH_H2H_1X2")
        self.assertEqual(r["cached_prop_line_coverage_events"], 7)
        self.assertTrue(r["cached_metadata_valid"])
        self.assertTrue(r["cached_metadata_recent"])
        self.assertFalse(r["raw_market_bytes_available"])
        self.assertIn("PROPLINE_COUNTS_ONLY_NO_NATIVE_QUOTE_OR_MODEL_SNAPSHOT",
                      r["blockers"])

    def test_old_141_credits_below_j1_reserve(self):
        r = self.audit()
        self.assertEqual(r["cached_odds_api_remaining"], 141)
        self.assertEqual(r["j1_odds_reserve_credits"], 220)
        self.assertIn("ODDS_API_J1_RESERVE_PROTECTED", r["blockers"])
        self.assertTrue(r["cached_quota_is_not_current"])
        self.assertFalse(r["new_odds_request_allowed"])

    def test_exact_220_still_reserves_credits(self):
        d = sample()
        d["j1_free_prematch_sources"][2]["quota_remaining"] = 220
        self.assertIn("ODDS_API_J1_RESERVE_PROTECTED", self.audit(d)["blockers"])

    def test_more_than_220_cached_credits_still_no_authorization(self):
        d = sample()
        d["j1_free_prematch_sources"][2]["quota_remaining"] = 221
        r = self.audit(d)
        self.assertIn("CACHED_ODDS_API_QUOTA_CANNOT_AUTHORIZE_NEW_REQUEST",
                      r["blockers"])
        self.assertFalse(r["new_odds_request_allowed"])

    def test_missing_quota_never_defaults_to_unlimited(self):
        d = sample()
        del d["j1_free_prematch_sources"][2]["quota_remaining"]
        r = self.audit(d)
        self.assertIsNone(r["cached_odds_api_remaining"])
        self.assertIn("ODDS_API_REMAINING_NOT_IN_CACHED_METADATA", r["blockers"])

    def test_boolean_quota_poisoned_before_reporting(self):
        d = sample()
        d["j1_free_prematch_sources"][2]["quota_remaining"] = True
        r = self.audit(d)
        self.assertFalse(r["cached_metadata_valid"])
        self.assertEqual(r["blockers"], ["INVALID_OR_EXPIRED_PUBLIC_J1_METADATA"])

    def test_meta_older_than_two_hours_blocks_shadow(self):
        r = self.audit(age=MAX_DIAGNOSTIC_AGE + timedelta(seconds=1))
        self.assertTrue(r["cached_metadata_valid"])
        self.assertFalse(r["cached_metadata_recent"])
        self.assertIn("CACHED_J1_METADATA_TOO_OLD_FOR_SHADOW_DIAGNOSTIC", r["blockers"])
        self.assertFalse(r["shadow_model_scoring_eligible"])

    def test_two_hour_boundary_is_only_diagnostic_not_model_ready(self):
        r = self.audit(age=MAX_DIAGNOSTIC_AGE)
        self.assertTrue(r["cached_metadata_recent"])
        self.assertEqual(r["certified_forward_samples"], 0)
        self.assertFalse(r["shadow_model_scoring_eligible"])

    def test_48_hours_ago_or_older_publication_rejected(self):
        r = self.audit(age=timedelta(hours=49))
        self.assertFalse(r["cached_metadata_valid"])
        self.assertEqual(r["blockers"], ["INVALID_OR_EXPIRED_PUBLIC_J1_METADATA"])

    def test_future_publication_cannot_qualify(self):
        r = self.audit(age=timedelta(minutes=-6))
        self.assertFalse(r["cached_metadata_valid"])
        self.assertEqual(r["blockers"], ["INVALID_OR_EXPIRED_PUBLIC_J1_METADATA"])

    def test_unknown_or_naive_assessment_clock_fail_closed(self):
        for bad in ("2026-11-23T00:00:00Z", None, datetime(2026, 11, 23), [], True):
            if bad is None:
                continue  # None intentionally means current UTC in public API.
            r = assess(sample(), now=bad)
            self.assertEqual(r["blockers"], ["INVALID_ASSESSMENT_CLOCK"])
            self.assertFalse(r["network_collection_allowed"])

    def test_therundown_missing_is_not_independent_second_source(self):
        r = self.audit()
        self.assertIn("THERUNDOWN_NOT_CONFIGURED_IN_SNAPSHOT", r["blockers"])
        self.assertIn("NO_MATCHED_TWO_API_J1_FIXTURE_COMPARISONS", r["blockers"])
        self.assertFalse(r["two_sources_independently_verified"])

    def test_nonzero_cross_api_count_still_not_verified_books(self):
        d = sample()
        d["cross_feed_consistency_observation"][
            "same_fixture_two_api_observations"] = 1
        d["cross_feed_consistency_observation"][
            "median_abs_home_probability_delta"] = 0.12
        r = self.audit(d)
        self.assertEqual(r["cached_two_api_fixture_comparisons"], 1)
        self.assertIn("TWO_API_COVERAGE_NOT_INDEPENDENT_BOOKMAKER_VERIFICATION",
                      r["blockers"])
        self.assertFalse(r["two_sources_independently_verified"])

    def test_missing_prop_research_coverage_is_not_invented(self):
        d = sample()
        row = d["j1_free_prematch_sources"][0]
        row["status"] = "HOLD"
        for key in ("fresh_3way_event_count", "fresh_spread_event_count",
                    "fresh_totals_event_count"):
            row[key] = 0
        d["status"] = "HOLD"
        r = self.audit(d)
        self.assertEqual(r["cached_prop_line_coverage_events"], 0)
        self.assertIn("NO_PROP_LINE_H2H_COVERAGE_IN_SNAPSHOT", r["blockers"])

    def test_unsupported_user_override_is_rejected_by_publisher_guard(self):
        d = sample()
        d["allow_betting"] = True
        r = self.audit(d)
        self.assertEqual(r["blockers"], ["INVALID_OR_EXPIRED_PUBLIC_J1_METADATA"])
        self.assertEqual(r["decision"], "HOLD")

    def test_injected_positive_ev_or_raw_odds_are_rejected(self):
        for field in ("positive_ev", "raw_bookmaker_prices", "research_recommendation"):
            d = sample()
            d[field] = 2.31
            r = self.audit(d)
            self.assertFalse(r["cached_metadata_valid"])
            self.assertFalse(r["positive_ev_verified"])

    def test_broken_snapshot_and_missing_required_flags_fail_closed(self):
        for bad in (None, [], {"schema": "bad"}):
            r = self.audit(bad)
            self.assertFalse(r["cached_metadata_valid"])
            self.assertFalse(r["network_collection_allowed"])
        d = sample()
        d["production_recommendations"] = "ENABLED"
        self.assertFalse(self.audit(d)["cached_metadata_valid"])

    def test_no_api_request_is_made_even_when_source_appears_ready(self):
        d = sample()
        d["j1_free_prematch_sources"][2]["quota_remaining"] = 10000
        with patch("japan_free_market.fetch", side_effect=AssertionError("network!")) as net, \
             patch("japan_free_market.odds_retrieve", side_effect=AssertionError("credits!")) as odds:
            r = self.audit(d)
        net.assert_not_called()
        odds.assert_not_called()
        self.assertEqual(r["requests_performed"], 0)
        self.assertEqual(r["api_credits_spent"], 0)
        self.assertFalse(r["new_odds_request_allowed"])

    def test_readonly_input_and_deterministic_output(self):
        d = sample()
        before = copy.deepcopy(d)
        a, b = self.audit(d), self.audit(d)
        self.assertEqual(d, before)
        self.assertEqual(a, b)
        self.assertIsNone(a["stake"])
        self.assertIsNone(a["research_recommendation"])

    def test_cli_prints_safe_snapshot_diagnostics_and_exit_hold(self):
        d = sample()
        d["collected_utc"] = datetime.now(timezone.utc).isoformat()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "sanitized.json"
            p.write_text(json.dumps(d), encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--status-file", str(p)])
        r = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["cached_prop_line_coverage_events"], 7)
        self.assertNotIn("X-API-Key", output.getvalue())
        self.assertNotIn('"price"', output.getvalue())

    def test_missing_file_is_hold_without_creating_it(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "missing.json"
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["--status-file", str(p)])
            self.assertEqual(code, 2)
            r = json.loads(output.getvalue())
            self.assertEqual(r["blockers"], ["MISSING_OR_UNREADABLE_J1_METADATA"])
            self.assertFalse(p.exists())


if __name__ == "__main__":
    unittest.main()
