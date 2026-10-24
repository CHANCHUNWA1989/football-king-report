"""Offline tests for zero-credit cached market health audit."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_health_audit import audit


class MarketHealthAuditTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 5, tzinfo=timezone.utc)
        self.market = {
            "as_of_utc": (self.now - timedelta(minutes=5)).isoformat(),
            "status": "RESEARCH_ONLY", "market": "h2h",
            "requested_markets": ["h2h"], "event_count": 1,
            "events": [{"market_last_update_utc": (self.now - timedelta(minutes=8)).isoformat(),
                        "kickoff_utc": (self.now + timedelta(hours=2)).isoformat()}],
            "missing_markets": [],
        }
        self.status = {
            "as_of_utc": self.market["as_of_utc"],
            "collection_status": "RESEARCH_ONLY",
            "quota": {"used": 322, "remaining": 178},
        }

    def test_fresh_cache_stays_research_only(self):
        result = audit(self.market, self.status, now=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_spreads_and_totals_forces_hold(self):
        self.market["missing_markets"] = ["spreads", "totals"]
        result = audit(self.market, self.status, now=self.now)
        self.assertIn("UNVERIFIED_MARKET_COVERAGE", result["reasons"])
        self.assertFalse(result["executable_odds_verified"])

    def test_market_readiness_is_separate(self):
        result = audit(self.market, self.status, now=self.now)
        self.assertEqual(result["market_readiness"]["h2h"], "RESEARCH_ONLY")
        self.assertEqual(result["market_readiness"]["totals"], "HOLD")
        self.assertEqual(result["market_readiness"]["spreads"], "HOLD")

    def test_missing_declared_h2h_is_hold(self):
        self.market["requested_markets"] = []
        result = audit(self.market, self.status, now=self.now)
        self.assertEqual(result["market_readiness"]["h2h"], "HOLD")
        self.assertIn("UNVERIFIED_1X2_SOURCE", result["reasons"])

    def test_old_snapshot_is_hold(self):
        result = audit(self.market, self.status, now=self.now + timedelta(hours=4))
        self.assertIn("SNAPSHOT_STALE_OR_FUTURE", result["reasons"])

    def test_old_quote_is_hold(self):
        self.market["events"][0]["market_last_update_utc"] = (
            self.now - timedelta(hours=2)).isoformat()
        self.assertIn("STALE_EVENT_QUOTES", audit(self.market, self.status, now=self.now)["reasons"])

    def test_quote_ages_while_cache_waits(self):
        result = audit(self.market, self.status, now=self.now + timedelta(minutes=40))
        self.assertIn("STALE_EVENT_QUOTES", result["reasons"])

    def test_quote_after_capture_is_hold(self):
        self.market["events"][0]["market_last_update_utc"] = (
            self.now - timedelta(minutes=1)).isoformat()
        result = audit(self.market, self.status, now=self.now)
        self.assertIn("STALE_EVENT_QUOTES", result["reasons"])

    def test_started_fixture_is_hold(self):
        self.market["events"][0]["kickoff_utc"] = (self.now - timedelta(minutes=1)).isoformat()
        result = audit(self.market, self.status, now=self.now)
        self.assertIn("LIVE_OR_FINISHED_EVENT_IN_CACHE", result["reasons"])

    def test_missing_kickoff_fails_closed(self):
        del self.market["events"][0]["kickoff_utc"]
        with self.assertRaises(KeyError):
            audit(self.market, self.status, now=self.now)

    def test_quota_floor_is_hold(self):
        self.status["quota"]["remaining"] = 140
        self.assertIn("QUOTA_GUARD", audit(self.market, self.status, now=self.now)["reasons"])

    def test_mismatched_archive_is_hold(self):
        self.status["as_of_utc"] = self.now.isoformat()
        self.assertIn("STATUS_MARKET_MISMATCH", audit(self.market, self.status, now=self.now)["reasons"])

    def test_bad_event_count_fails_closed(self):
        self.market["event_count"] = 2
        with self.assertRaises(ValueError):
            audit(self.market, self.status, now=self.now)


if __name__ == "__main__":
    unittest.main()
