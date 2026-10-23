"""Offline checks for local entitlement file isolation."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_local_registry_entry import admit_from_local_registry


class TestLocalRegistryEntry(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        stamp = self.now.isoformat()
        verified = (self.now - timedelta(days=1)).isoformat()
        expires = (self.now + timedelta(days=1)).isoformat()
        self.raw = {
            "match": {"provider": "scores", "event_id": "e1", "licensed": True,
                      "state": "LIVE", "elapsed_minute": 40, "home_score": 1,
                      "away_score": 0, "updated_at": stamp},
            "market": {"provider": "odds", "event_id": "e1", "licensed": True,
                       "bookmaker": "example", "market_key": "totals",
                       "outcome": "over_2.5", "updated_at": stamp,
                       "price": 1.91, "in_play": True},
        }
        self.registry = {
            "scores": {"admin_verified": True, "research_use": True,
                       "live_scores": True, "verified_at_utc": verified,
                       "expires_at_utc": expires},
            "odds": {"admin_verified": True, "research_use": True,
                     "live_odds": True, "verified_at_utc": verified,
                     "expires_at_utc": expires},
        }

    def test_no_registry_path_holds(self):
        result = admit_from_local_registry(self.raw, now=self.now)
        self.assertEqual(result["status"], "HOLD")

    def test_provider_supplied_registry_does_not_count(self):
        raw = {**self.raw, "entitlements": self.registry}
        result = admit_from_local_registry(raw, now=self.now)
        self.assertEqual(result["status"], "HOLD")

    def test_valid_separate_file_is_research_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rights.json"
            path.write_text(json.dumps(self.registry), encoding="utf-8")
            result = admit_from_local_registry(self.raw, registry_path=path, now=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_malformed_registry_holds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rights.json"
            path.write_text("{broken", encoding="utf-8")
            result = admit_from_local_registry(self.raw, registry_path=path, now=self.now)
        self.assertEqual(result["status"], "HOLD")

    def test_missing_registry_holds(self):
        result = admit_from_local_registry(self.raw, registry_path="/nonexistent/rights.json", now=self.now)
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
