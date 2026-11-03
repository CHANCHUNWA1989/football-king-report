"""Synthetic-only tests for the fail-closed live evidence cut."""
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_quote_snapshot_guard import audit_live_snapshot, main


def sample():
    return {
        "event_id": "synthetic-fixture-123",
        "kickoff_utc": "2026-10-31T08:00:00Z",
        "decision_utc": "2026-10-31T08:30:00Z",
        "score": {
            "event_id": "synthetic-fixture-123", "source": "sample-official",
            "upstream_updated_utc": "2026-10-31T08:29:50Z",
            "captured_utc": "2026-10-31T08:29:55Z",
            "home_goals": 0, "away_goals": 0,
            "last_material_event_utc": "2026-10-31T08:00:00Z",
        },
        "stats": {
            "event_id": "synthetic-fixture-123", "source": "sample-stats",
            "upstream_updated_utc": "2026-10-31T08:29:53Z",
            "captured_utc": "2026-10-31T08:29:56Z",
            "home_xg": 0.1, "away_xg": 0.3,
        },
        "quote": {
            "event_id": "synthetic-fixture-123", "source": "sample-licensed-odds",
            "upstream_updated_utc": "2026-10-31T08:29:56Z",
            "captured_utc": "2026-10-31T08:29:58Z",
            "market": "totals", "selection": "over", "in_play": True,
            "line": 2.25, "decimal_price": 1.91, "bookmaker": "sample-book",
        },
    }


class LiveQuoteSnapshotGuardTests(unittest.TestCase):
    def test_fresh_input_is_research_only_not_positive_ev(self):
        output = audit_live_snapshot(sample())
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertFalse(output["certified_positive_ev"])
        self.assertFalse(output["market_executable_verified"])
        self.assertFalse(output["probability_calibrated"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_stale_upstream_rejected_despite_recent_capture(self):
        s = sample()
        s["stats"]["upstream_updated_utc"] = "2026-10-31T08:20:00Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_stats_before_goal_rejected(self):
        s = sample()
        s["score"]["last_material_event_utc"] = "2026-10-31T08:29:50Z"
        s["stats"]["upstream_updated_utc"] = "2026-10-31T08:29:49Z"
        self.assertIn("STATS_BEFORE_MATERIAL_EVENT", audit_live_snapshot(s)["reasons"])

    def test_quote_before_goal_rejected(self):
        s = sample()
        s["score"]["home_goals"] = 1
        s["score"]["last_material_event_utc"] = "2026-10-31T08:29:52Z"
        s["score"]["upstream_updated_utc"] = "2026-10-31T08:29:55Z"
        s["quote"]["upstream_updated_utc"] = "2026-10-31T08:29:51Z"
        self.assertIn("QUOTE_BEFORE_MATERIAL_EVENT", audit_live_snapshot(s)["reasons"])

    def test_var_cancellation_rejects_older_odds(self):
        s = sample()
        s["score"]["last_material_event_utc"] = "2026-10-31T08:29:57Z"
        s["score"]["upstream_updated_utc"] = "2026-10-31T08:29:58Z"
        s["score"]["captured_utc"] = "2026-10-31T08:29:59Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_clock_heartbeat_after_quote_does_not_false_hold(self):
        s = sample()
        s["score"]["upstream_updated_utc"] = "2026-10-31T08:29:58Z"
        s["score"]["captured_utc"] = "2026-10-31T08:29:59Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "RESEARCH_ONLY")

    def test_missing_material_event_timestamp_fails_closed(self):
        s = sample()
        del s["score"]["last_material_event_utc"]
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_other_match_quote_rejected(self):
        s = sample()
        s["quote"]["event_id"] = "another-event"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_future_quote_rejected(self):
        s = sample()
        s["quote"]["upstream_updated_utc"] = "2026-10-31T08:31:00Z"
        s["quote"]["captured_utc"] = "2026-10-31T08:31:01Z"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_missing_line_rejected(self):
        s = sample()
        del s["quote"]["line"]
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_boolean_odds_rejected(self):
        s = sample()
        s["quote"]["decimal_price"] = True
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_naive_timestamp_rejected(self):
        s = sample()
        s["decision_utc"] = "2026-10-31T08:30:00"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_unsupported_selection_rejected(self):
        s = sample()
        s["quote"]["selection"] = "away"
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_pre_match_quote_rejected(self):
        s = sample()
        s["quote"]["in_play"] = False
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_quarter_line_rejected(self):
        s = sample()
        s["quote"]["line"] = 2.30
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_xg_rejected(self):
        s = sample()
        s["stats"]["away_xg"] = float("nan")
        self.assertEqual(audit_live_snapshot(s)["status"], "HOLD")

    def test_invalid_age_limit_rejected(self):
        self.assertEqual(audit_live_snapshot(sample(), max_age_seconds=float("inf"))["status"], "HOLD")

    def test_asian_handicap_side_supported_but_not_ev(self):
        s = sample()
        s["quote"]["market"] = "asian_handicap"
        s["quote"]["selection"] = "away"
        s["quote"]["line"] = 0.75
        output = audit_live_snapshot(s)
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertFalse(output["certified_positive_ev"])


    def _corner_sample(self):
        evidence = sample()
        evidence["quote"].update({
            "market": "corners_totals", "selection": "over",
            "line": 8.5, "decimal_price": 1.90,
        })
        evidence["score"]["match_status"] = "FIRST_HALF"
        evidence["stats"].pop("home_xg")
        evidence["stats"].pop("away_xg")
        evidence["stats"].update({
            "home_corners": 4, "away_corners": 4,
            "last_corner_event_utc": "2026-10-31T08:29:51Z",
        })
        source_ids = {
            "score": ("score-event-123", "https://score.example.org/matches/123"),
            "stats": ("stats-event-123", "https://stats.example.org/fixtures/123"),
            "quote": ("quote-event-123", "https://odds.example.org/events/123"),
        }
        for key, (native_id, url) in source_ids.items():
            evidence[key]["source_event_id"] = native_id
            evidence[key]["source_url"] = url
        return evidence

    def _trusted_fixture(self):
        evidence = self._corner_sample()
        return {
            "event_id": evidence["event_id"],
            "kickoff_utc": evidence["kickoff_utc"],
            "registered_at_utc": "2026-10-31T07:40:00Z",
            "source_events": {
                key: {
                    "source": evidence[key]["source"],
                    "source_event_id": evidence[key]["source_event_id"],
                    "source_url": evidence[key]["source_url"],
                }
                for key in ("score", "stats", "quote")
            },
        }

    def _audit_corner(self, evidence, fixture=None):
        return audit_live_snapshot(
            evidence,
            trusted_fixture=self._trusted_fixture() if fixture is None else fixture,
        )

    def test_corner_market_live_not_decided_is_research_only(self):
        evidence = self._corner_sample()
        result = self._audit_corner(evidence)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["certified_positive_ev"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_corner_market_quote_before_latest_corner_is_hold(self):
        evidence = self._corner_sample()
        evidence["stats"]["last_corner_event_utc"] = "2026-10-31T08:29:55Z"
        evidence["stats"]["upstream_updated_utc"] = "2026-10-31T08:29:56Z"
        evidence["stats"]["captured_utc"] = "2026-10-31T08:29:57Z"
        evidence["quote"]["upstream_updated_utc"] = "2026-10-31T08:29:54Z"
        self.assertIn("QUOTE_BEFORE_CORNER_EVENT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_stats_before_latest_corner_is_hold(self):
        evidence = self._corner_sample()
        evidence["stats"]["last_corner_event_utc"] = "2026-10-31T08:29:54Z"
        self.assertIn("STATS_BEFORE_CORNER_EVENT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_missing_corner_event_is_hold(self):
        evidence = self._corner_sample()
        del evidence["stats"]["last_corner_event_utc"]
        self.assertEqual(self._audit_corner(evidence)["status"], "HOLD")

    def test_corner_market_missing_counters_is_hold(self):
        evidence = self._corner_sample()
        del evidence["stats"]["away_corners"]
        self.assertEqual(self._audit_corner(evidence)["status"], "HOLD")

    def test_corner_market_rejects_boolean_or_negative_corner_counts(self):
        for bad in (True, -1, 2.5, None):
            with self.subTest(count=bad):
                evidence = self._corner_sample()
                evidence["stats"]["home_corners"] = bad
                self.assertEqual(self._audit_corner(evidence)["status"], "HOLD")

    def test_corner_market_already_decided_over_is_hold(self):
        evidence = self._corner_sample()
        evidence["stats"]["home_corners"] = 5  # 9 corners, >8.5
        self.assertIn("CORNER_MARKET_ALREADY_DECIDED",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_already_decided_under_is_hold(self):
        evidence = self._corner_sample()
        evidence["quote"]["selection"] = "under"
        evidence["stats"]["away_corners"] = 5
        self.assertIn("CORNER_MARKET_ALREADY_DECIDED",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_zero_corners_requires_kickoff_anchor(self):
        evidence = self._corner_sample()
        evidence["stats"].update({
            "home_corners": 0, "away_corners": 0,
            "last_corner_event_utc": "2026-10-31T08:00:00Z",
        })
        self.assertEqual(self._audit_corner(evidence)["status"], "RESEARCH_ONLY")
        evidence["stats"]["last_corner_event_utc"] = "2026-10-31T08:05:00Z"
        self.assertIn("INVALID_ZERO_CORNER_ANCHOR",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_nonzero_corners_cannot_use_kickoff_anchor(self):
        evidence = self._corner_sample()
        evidence["stats"]["last_corner_event_utc"] = evidence["kickoff_utc"]
        self.assertIn("INVALID_CORNER_EVENT_ANCHOR",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_rejects_missing_match_status(self):
        evidence = self._corner_sample()
        del evidence["score"]["match_status"]
        self.assertIn("MATCH_STATUS_MISSING_OR_INVALID",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_rejects_terminal_or_ambiguous_match_status(self):
        for status in ("FINISHED", "FT", "ABANDONED", "SUSPENDED",
                       "POSTPONED", "NOT_STARTED", "EXTRA_TIME", "PENALTIES",
                       "UNKNOWN", None, True, 0):
            with self.subTest(status=status):
                evidence = self._corner_sample()
                evidence["score"]["match_status"] = status
                self.assertEqual(self._audit_corner(evidence)["status"], "HOLD")

    def test_corner_market_allows_regulation_half_time(self):
        evidence = self._corner_sample()
        evidence["score"]["match_status"] = "HALF_TIME"
        evidence["decision_utc"] = "2026-10-31T08:46:00Z"
        for record in ("score", "stats", "quote"):
            evidence[record]["upstream_updated_utc"] = "2026-10-31T08:45:52Z"
            evidence[record]["captured_utc"] = "2026-10-31T08:45:55Z"
        self.assertEqual(self._audit_corner(evidence)["status"], "RESEARCH_ONLY")

    def test_corner_market_allows_regulation_second_half(self):
        evidence = self._corner_sample()
        evidence["score"]["match_status"] = "SECOND_HALF"
        evidence["decision_utc"] = "2026-10-31T09:12:00Z"
        for record in ("score", "stats", "quote"):
            evidence[record]["upstream_updated_utc"] = "2026-10-31T09:11:52Z"
            evidence[record]["captured_utc"] = "2026-10-31T09:11:55Z"
        self.assertEqual(self._audit_corner(evidence)["status"], "RESEARCH_ONLY")

    def test_corner_market_rejects_implausible_status_clock(self):
        evidence = self._corner_sample()
        evidence["score"]["match_status"] = "SECOND_HALF"
        self.assertIn("MATCH_STATUS_CLOCK_CONFLICT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_rejects_very_late_false_second_half(self):
        evidence = self._corner_sample()
        evidence["decision_utc"] = "2026-10-31T11:00:00Z"
        # Refresh upstream timestamps so age check does not mask the bad clock.
        for record in ("score", "stats", "quote"):
            evidence[record]["upstream_updated_utc"] = "2026-10-31T10:59:53Z"
            evidence[record]["captured_utc"] = "2026-10-31T10:59:56Z"
        evidence["score"]["match_status"] = "SECOND_HALF"
        self.assertIn("MATCH_STATUS_CLOCK_CONFLICT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_missing_prior_fixture_binding_is_hold(self):
        evidence = self._corner_sample()
        result = audit_live_snapshot(evidence)
        self.assertEqual(result["status"], "HOLD")
        self.assertIn("TRUSTED_FIXTURE_REQUIRED", result["reasons"])

    def test_corner_market_mismatched_native_provider_event_id_is_hold(self):
        evidence = self._corner_sample()
        evidence["stats"]["source_event_id"] = "other-event"
        self.assertIn("SOURCE_EVENT_IDENTITY_CONFLICT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_mismatched_source_url_is_hold(self):
        evidence = self._corner_sample()
        evidence["quote"]["source_url"] = "https://odds.example.org/events/other"
        self.assertIn("SOURCE_EVENT_IDENTITY_CONFLICT",
                      self._audit_corner(evidence)["reasons"])

    def test_corner_market_source_url_must_be_https(self):
        evidence = self._corner_sample()
        fixture = self._trusted_fixture()
        evidence["stats"]["source_url"] = "http://stats.example.org/fixtures/123"
        fixture["source_events"]["stats"]["source_url"] = evidence["stats"]["source_url"]
        self.assertIn("INVALID_SOURCE_URL",
                      self._audit_corner(evidence, fixture)["reasons"])

    def test_corner_market_rejects_tokenized_public_source_urls(self):
        # The source map is publicly committed and can be published in
        # Sigstore artifacts. Query parameters might reveal API credentials.
        for suffix in ("?api_key=sample-do-not-use", "?token=dummy", "?match=123"):
            with self.subTest(suffix=suffix):
                evidence = self._corner_sample()
                fixture = self._trusted_fixture()
                path = "https://stats.example.org/fixtures/123" + suffix
                evidence["stats"]["source_url"] = path
                fixture["source_events"]["stats"]["source_url"] = path
                self.assertIn(
                    "INVALID_SOURCE_URL",
                    self._audit_corner(evidence, fixture)["reasons"],
                )

    def test_corner_market_fixture_binding_must_precede_kickoff(self):
        evidence = self._corner_sample()
        fixture = self._trusted_fixture()
        fixture["registered_at_utc"] = "2026-10-31T08:10:00Z"
        self.assertIn("FIXTURE_NOT_PRE_REGISTERED",
                      self._audit_corner(evidence, fixture)["reasons"])

    def test_corner_market_wrong_kickoff_or_fixture_is_hold(self):
        evidence = self._corner_sample()
        fixture = self._trusted_fixture()
        fixture["kickoff_utc"] = "2026-10-31T08:05:00Z"
        self.assertIn("FIXTURE_BINDING_CONFLICT",
                      self._audit_corner(evidence, fixture)["reasons"])
        fixture = self._trusted_fixture()
        fixture["event_id"] = "different-fixture"
        self.assertIn("FIXTURE_BINDING_CONFLICT",
                      self._audit_corner(evidence, fixture)["reasons"])

    def test_corner_market_invalid_binding_schema_is_hold(self):
        evidence = self._corner_sample()
        for bad in (None, {}, [], {"event_id": evidence["event_id"]}):
            with self.subTest(binding=repr(bad)):
                result = audit_live_snapshot(evidence, trusted_fixture=bad)
                self.assertEqual(result["status"], "HOLD")

    def test_goal_totals_legacy_evidence_does_not_need_corner_binding(self):
        evidence = sample()
        self.assertEqual(audit_live_snapshot(evidence)["status"], "RESEARCH_ONLY")

    def test_goal_total_still_requires_xg(self):
        evidence = sample()
        del evidence["stats"]["home_xg"]
        self.assertEqual(audit_live_snapshot(evidence)["status"], "HOLD")


    def test_cli_research_only_with_recent_synthetic_evidence(self):
        now = datetime.now(timezone.utc)
        evidence = sample()
        kick = now - timedelta(minutes=20)
        evidence["kickoff_utc"] = kick.isoformat()
        evidence["score"]["last_material_event_utc"] = kick.isoformat()
        for field, n in (("score", 8), ("stats", 6), ("quote", 4)):
            evidence[field]["upstream_updated_utc"] = (now - timedelta(seconds=n)).isoformat()
            evidence[field]["captured_utc"] = (now - timedelta(seconds=n - 1)).isoformat()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "synthetic.json"
            target.write_text(json.dumps(evidence), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                exit_code = main([str(target)])
        self.assertEqual(exit_code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["certified_positive_ev"])
        self.assertNotIn("sample-book", output.getvalue())

    def test_cli_missing_file_is_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            output = StringIO()
            with redirect_stdout(output):
                code = main([str(Path(folder) / "not-found.json")])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "HOLD")

    def test_cli_invalid_json_is_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "broken.json"
            target.write_text("{invalid-json", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = main([str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
