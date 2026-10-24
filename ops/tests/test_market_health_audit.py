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
            "status": "RESEARCH_ONLY", "event_count": 1,
            "events": [{"market_last_update_utc": (self.now - timedelta(minutes=8)).isoformat()}],
            "missing_markets": ["spreads", "totals"],
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

    def test_old_snapshot_is_hold(self):
        result = audit(self.market, self.status, now=self.now + timedelta(hours=4))
        self.assertIn("SNAPSHOT_STALE_OR_FUTURE", result["reasons"])

    def test_old_quote_is_hold(self):
        self.market["events"][0]["market_last_update_utc"] = (
            self.now - timedelta(hours=2)).isoformat()
        self.assertIn("STALE_EVENT_QUOTES", audit(self.market, self.status, now=self.now)["reasons"])

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
