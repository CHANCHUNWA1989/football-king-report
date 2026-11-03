import unittest
from datetime import datetime, timedelta, timezone

from ops.control_tower_monitor import (
    build_snapshot, market_health, github_health, github_api
)

NOW = datetime(2026, 11, 3, 14, 35, tzinfo=timezone.utc)
GOOD = {"schema": "football-king-market-consensus-v1", "market": "h2h",
        "status": "RESEARCH_ONLY", "as_of_utc": "2026-11-03T14:12:46Z",
        "event_count": 91, "quota": {"remaining": 443}}
SHA = "a" * 40


class ControlTowerTests(unittest.TestCase):
    def test_fresh_stays_research_only(self):
        actual = market_health(GOOD, NOW)
        self.assertEqual(actual["state"], "CURRENT_RESEARCH_ONLY")
        self.assertEqual(actual["event_count"], 91)
        self.assertEqual(actual["reason"], "H2H_ONLY_NOT_EXECUTABLE")

    def test_stale_fails_closed_without_current_events(self):
        data = dict(GOOD, as_of_utc=(NOW - timedelta(hours=11)).isoformat())
        actual = market_health(data, NOW)
        self.assertEqual(actual["state"], "HOLD")
        self.assertIsNone(actual["event_count"])

    def test_future_timestamp_rejected(self):
        data = dict(GOOD, as_of_utc=(NOW + timedelta(minutes=7)).isoformat())
        self.assertEqual(market_health(data, NOW)["reason"], "FUTURE_SOURCE_CLOCK")

    def test_missing_timezone_rejected(self):
        data = dict(GOOD, as_of_utc="2026-11-03T14:12:46")
        self.assertEqual(market_health(data, NOW)["state"], "HOLD")

    def test_malformed_counts_rejected(self):
        data = dict(GOOD, event_count=True)
        self.assertEqual(market_health(data, NOW)["reason"], "INVALID_MARKET_COUNTS")

    def test_wrong_market_or_status_rejected(self):
        for data in (dict(GOOD, market="totals"),
                     dict(GOOD, status="READY")):
            self.assertEqual(market_health(data, NOW)["state"], "HOLD")

    def test_no_github_never_claims_current_ci(self):
        snap = build_snapshot(GOOD, now=NOW)
        self.assertEqual(snap["monitor_state"], "HOLD_INCOMPLETE_EVIDENCE")
        self.assertTrue(all(p["ci_sample"] == "UNVERIFIED"
                            for p in snap["github"]["watched_prs"]))
        self.assertEqual(snap["production_gate"]["status"], "HOLD")
        self.assertFalse(snap["production_gate"]["live_execution_allowed"])

    def test_sample_ci_not_full_approval(self):
        item = {"number": 400, "draft": True, "head": {"sha": SHA}}
        run = {"head_sha": SHA, "event": "pull_request", "status": "completed",
               "conclusion": "success"}
        actual = github_health(
            {"commit": {"sha": SHA}, "protected": False},
            [item], {"workflow_runs": [run]}
        )
        self.assertEqual(actual["watched_prs"][-1]["ci_sample"],
                         "OBSERVED_PASS_NOT_EXHAUSTIVE")
        self.assertEqual(actual["watched_prs"][0]["state"], "UNKNOWN")
        self.assertFalse(actual["main_protected"])

    def test_workflow_in_progress(self):
        item = {"number": 400, "head": {"sha": SHA}}
        run = {"head_sha": SHA, "event": "pull_request",
               "status": "in_progress", "conclusion": None}
        actual = github_health(None, [item], {"workflow_runs": [run]})
        self.assertEqual(actual["watched_prs"][-1]["ci_sample"], "IN_PROGRESS")

    def test_endpoint_allowlist(self):
        with self.assertRaises(ValueError):
            github_api("repos/../secrets")

    def test_empty_input_fail_closed(self):
        snap = build_snapshot(None, now=NOW)
        self.assertEqual(snap["market"]["state"], "HOLD")
        self.assertEqual(snap["production_gate"]["production_recommendations"],
                         "DISABLED")


if __name__ == "__main__":
    unittest.main()
