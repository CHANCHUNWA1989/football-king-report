"""Synthetic tests for explicit licensed-provider mapping."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_provider_adapter import normalize_and_admit


class TestLiveProviderAdapter(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        stamp = self.now.isoformat()
        self.raw = {
            "match": {"event_id": "f1", "licensed": True, "state": "LIVE",
                      "elapsed_minute": 66, "home_score": 1, "away_score": 0,
                      "updated_at": stamp},
            "market": {"event_id": "f1", "licensed": True, "bookmaker": "example",
                       "market_key": "totals", "outcome": "over_2.5",
                       "updated_at": stamp, "price": 1.94,
                       "in_play": True, "consensus": False},
        }

    def test_authorized_fresh_feed_is_research_only(self):
        result = normalize_and_admit(self.raw, now=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_license_holds(self):
        raw = {**self.raw, "market": {**self.raw["market"], "licensed": False}}
        self.assertEqual(normalize_and_admit(raw, now=self.now)["status"], "HOLD")

    def test_consensus_holds(self):
        raw = {**self.raw, "market": {**self.raw["market"], "consensus": True}}
        self.assertEqual(normalize_and_admit(raw, now=self.now)["status"], "HOLD")

    def test_wrong_event_holds(self):
        raw = {**self.raw, "market": {**self.raw["market"], "event_id": "f2"}}
        self.assertEqual(normalize_and_admit(raw, now=self.now)["status"], "HOLD")

    def test_expired_score_holds(self):
        old = (self.now - timedelta(seconds=100)).isoformat()
        raw = {**self.raw, "match": {**self.raw["match"], "updated_at": old}}
        self.assertEqual(normalize_and_admit(raw, now=self.now)["status"], "HOLD")

    def test_missing_provider_payload_holds(self):
        for raw in (None, {}, {"match": {}}, {"market": {}}):
            with self.subTest(raw=raw):
                result = normalize_and_admit(raw, now=self.now)
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["observations"], [])


if __name__ == "__main__":
    unittest.main()
