"""Research-only consensus fallback cannot create fake executable odds."""
import sys
import tempfile
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_market_failover import route, publish


class MarketFallbackTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        self.primary = {"production_recommendations": "DISABLED",
                        "source_state": "RESEARCH_ONLY",
                        "market_as_of_utc": self.now.isoformat(),
                        "matched_count": 8}
        self.bsd = {"schema": "football-king-bsd-optional-market-overlay-v1",
                    "production_recommendations": "DISABLED",
                    "source_state": "RESEARCH_ONLY", "status": "RESEARCH_ONLY",
                    "market_is_executable": False,
                    "automatic_replacement_of_main_market": False,
                    "created_utc": self.now.isoformat(),
                    "last_source_checked_utc": self.now.isoformat(),
                    "time_valid_shadow_pairs": 3}

    def test_primary_priority(self):
        out = route(self.primary, self.bsd, now=self.now)
        self.assertEqual(out["status"], "PRIMARY_RESEARCH_CONSENSUS")
        self.assertFalse(out["executable_bookmaker_quote_available"])
        self.assertFalse(out["positive_ev_verified"])

    def test_missing_primary_uses_valid_bsd_only_as_research(self):
        out = route(None, self.bsd, now=self.now)
        self.assertEqual(out["status"], "BSD_FREE_RESEARCH_CONSENSUS_BACKUP")
        self.assertFalse(out["automatic_primary_market_substitution"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_expired_primary_and_bsd_both_hold(self):
        old = (self.now - timedelta(hours=19)).isoformat()
        self.primary["market_as_of_utc"] = old
        self.bsd["last_source_checked_utc"] = old
        out = route(self.primary, self.bsd, now=self.now)
        self.assertEqual(out["status"], "NO_FRESH_COMPARABLE_RESEARCH_MARKET")
        self.assertFalse(out["executable_bookmaker_quote_available"])

    def test_bsd_unconfigured_never_activates(self):
        self.bsd["status"] = "HOLD"
        self.assertEqual(route(None, self.bsd, now=self.now)["status"],
                         "NO_FRESH_COMPARABLE_RESEARCH_MARKET")

    def test_bsd_unsafe_quote_status_not_used(self):
        self.bsd["market_is_executable"] = True
        self.assertEqual(route(None, self.bsd, now=self.now)["status"],
                         "NO_FRESH_COMPARABLE_RESEARCH_MARKET")

    def test_invalid_market_timestamps_and_shapes_not_crash(self):
        self.primary["market_as_of_utc"] = "bad"
        self.bsd["last_source_checked_utc"] = "bad"
        self.assertEqual(route(self.primary, self.bsd, now=self.now)["status"],
                         "NO_FRESH_COMPARABLE_RESEARCH_MARKET")

    def test_missing_files_publish_safe_status(self):
        with tempfile.TemporaryDirectory() as folder:
            result = publish(folder)
            self.assertEqual(result["status"], "NO_FRESH_COMPARABLE_RESEARCH_MARKET")
            doc = json.loads((Path(folder) / "research_market_failover.json").read_text())
            self.assertFalse(doc["positive_ev_verified"])


if __name__ == "__main__":
    unittest.main()
