"""Synthetic end-to-end replay tests; no provider credentials or network."""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_research_replay import replay_live_research


class TestLiveResearchReplay(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        ts = self.now.isoformat()
        self.raw = {
            "match": {"provider": "scores", "event_id": "e1", "licensed": True,
                      "state": "LIVE", "elapsed_minute": 50, "home_score": 1,
                      "away_score": 1, "updated_at": ts},
            "market": {"provider": "odds", "event_id": "e1", "licensed": True,
                       "bookmaker": "example", "market_key": "totals",
                       "outcome": "over_2.5", "updated_at": ts,
                       "price": 1.9, "in_play": True},
        }
        before = (self.now - timedelta(days=1)).isoformat()
        after = (self.now + timedelta(days=1)).isoformat()
        self.registry = {
            "scores": {"admin_verified": True, "research_use": True,
                       "live_scores": True, "verified_at_utc": before,
                       "expires_at_utc": after},
            "odds": {"admin_verified": True, "research_use": True,
                     "live_odds": True, "verified_at_utc": before,
                     "expires_at_utc": after},
        }

    def test_mixed_replay_metrics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rights.json"
            path.write_text(json.dumps(self.registry), encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            stale = {**self.raw, "match": {**self.raw["match"],
                     "updated_at": (self.now - timedelta(seconds=120)).isoformat()}}
            result = replay_live_research([self.raw, stale], registry_path=path,
                                          expected_sha256=digest, now=self.now)
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["quality"]["accepted_research"], 1)
        self.assertEqual(result["quality"]["held"], 1)
        self.assertEqual(result["quality"]["hold_reasons"], {"STALE_SCORE": 1})
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_registry_all_held(self):
        result = replay_live_research([self.raw], now=self.now)
        self.assertEqual(result["quality"]["held"], 1)
        self.assertEqual(result["quality"]["accepted_research"], 0)

    def test_empty_and_invalid_batches(self):
        self.assertEqual(replay_live_research([])["status"], "HOLD")
        self.assertEqual(replay_live_research(None)["status"], "HOLD")
        self.assertEqual(replay_live_research([{}] * 10001)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
