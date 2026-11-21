import copy
import unittest
from datetime import datetime, timezone, timedelta
from ops.football_readiness_diagnostic import diagnose


def summary(now):
    return {
        "schema": "football-king-public-artifact-summary-v1",
        "captured_utc": (now - timedelta(minutes=2)).isoformat(),
        "input_status": "CONNECTED",
        "counts": {"RESEARCH_ONLY": 3678, "VERIFIED_VALUE": 0, "STALE": 0,
                   "INCOMPLETE": 0, "INVALID": 0, "NO_VALUE": 0},
        "coverage": [{"league": "epl", "quotes": 675, "status": "COUNTS_ONLY"},
                     {"league": "bundesliga", "quotes": 552, "status": "COUNTS_ONLY"}],
        "requested_markets": ["h2h"],
        "evidence_progress": {"independently_verified_result_cases": 0},
        "production_recommendations": "DISABLED",
        "raw_prices_or_bookmakers_included": False,
        "quotes_are_executable": False,
        "verified_bets": 0
    }


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)

    def test_connected_quotes_still_not_predictions(self):
        r = diagnose(summary(self.now), now=self.now)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["redacted_quote_count"], 1227)
        self.assertIn("LIVE_MODEL_FORECAST_AND_QUOTE_PAIRING_UNVERIFIED", r["blockers"])
        self.assertIn("ASIAN_HANDICAP_AND_TOTALS_NOT_COLLECTED", r["blockers"])
        self.assertFalse(r["recommendation_ready"])
        self.assertNotIn("odds", r)

    def test_stale_snapshot(self):
        s = summary(self.now)
        s["captured_utc"] = (self.now - timedelta(hours=2)).isoformat()
        self.assertIn("REDACTED_FEED_SUMMARY_STALE", diagnose(s, now=self.now)["blockers"])

    def test_unconnected_feed(self):
        s = summary(self.now)
        s["input_status"] = "MISSING_API_KEY"
        self.assertIn("PRIVATE_FEED_NOT_CONNECTED", diagnose(s, now=self.now)["blockers"])

    def test_missing_summary_holds(self):
        self.assertEqual(diagnose(None, now=self.now)["blockers"], ["NO_SAFE_PRIVATE_FEED_SUMMARY"])

    def test_malicious_unredacted_snapshot_holds(self):
        s = summary(self.now)
        s["raw_prices_or_bookmakers_included"] = True
        self.assertEqual(diagnose(s, now=self.now)["blockers"], ["INVALID_REDACTED_SUMMARY"])

    def test_future_capture_holds(self):
        s = summary(self.now)
        s["captured_utc"] = (self.now + timedelta(minutes=10)).isoformat()
        self.assertIn("REDACTED_FEED_SUMMARY_STALE", diagnose(s, now=self.now)["blockers"])

    def test_empty_market_snapshot_holds(self):
        s = summary(self.now)
        s["counts"]["RESEARCH_ONLY"] = 0
        for row in s["coverage"]:
            row["quotes"] = 0
        r = diagnose(s, now=self.now)
        self.assertIn("ZERO_COLLECTED_QUOTES", r["blockers"])
        self.assertIn("NO_RESEARCH_QUOTES", r["blockers"])


if __name__ == "__main__":
    unittest.main()
