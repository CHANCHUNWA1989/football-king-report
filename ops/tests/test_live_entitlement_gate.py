"""Offline tests for independent local entitlement policy."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_entitlement_gate import admit_with_registry


class TestEntitlementGate(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, tzinfo=timezone.utc)
        stamp = self.now.isoformat()
        self.raw = {
            "match": {"provider": "scores", "event_id": "e1", "licensed": True,
                      "state": "LIVE", "elapsed_minute": 40, "home_score": 0,
                      "away_score": 1, "updated_at": stamp},
            "market": {"provider": "odds", "event_id": "e1", "licensed": True,
                       "bookmaker": "example", "market_key": "totals",
                       "outcome": "over_2.5", "updated_at": stamp, "price": 1.88,
                       "in_play": True, "consensus": False},
        }
        verified = (self.now - timedelta(days=1)).isoformat()
        expires = (self.now + timedelta(days=30)).isoformat()
        self.registry = {
            "scores": {"admin_verified": True, "live_scores": True,
                       "research_use": True, "verified_at_utc": verified,
                       "expires_at_utc": expires},
            "odds": {"admin_verified": True, "live_odds": True,
                     "research_use": True, "verified_at_utc": verified,
                     "expires_at_utc": expires},
        }

    def test_verified_registry_research_only(self):
        result = admit_with_registry(self.raw, self.registry, now=self.now)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_provider_claim_alone_never_suffices(self):
        result = admit_with_registry(self.raw, {}, now=self.now)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["observations"], [])

    def test_wrong_capability_holds(self):
        registry = {**self.registry, "odds": {"admin_verified": True,
                    "live_scores": True, "research_use": True}}
        self.assertEqual(admit_with_registry(self.raw, registry, now=self.now)["status"], "HOLD")

    def test_unverified_registry_holds(self):
        registry = {**self.registry, "odds": {**self.registry["odds"], "admin_verified": False}}
        self.assertEqual(admit_with_registry(self.raw, registry, now=self.now)["status"], "HOLD")

    def test_expired_entitlement_holds(self):
        registry = {**self.registry, "odds": {**self.registry["odds"],
                    "expires_at_utc": (self.now - timedelta(seconds=1)).isoformat()}}
        self.assertEqual(admit_with_registry(self.raw, registry, now=self.now)["status"], "HOLD")

    def test_missing_expiry_holds(self):
        registry = {**self.registry, "odds": {**self.registry["odds"],
                    "expires_at_utc": None}}
        self.assertEqual(admit_with_registry(self.raw, registry, now=self.now)["status"], "HOLD")

    def test_future_verification_holds(self):
        registry = {**self.registry, "odds": {**self.registry["odds"],
                    "verified_at_utc": (self.now + timedelta(days=1)).isoformat()}}
        self.assertEqual(admit_with_registry(self.raw, registry, now=self.now)["status"], "HOLD")

    def test_missing_provider_identity_holds(self):
        raw = {**self.raw, "market": {**self.raw["market"], "provider": None}}
        self.assertEqual(admit_with_registry(raw, self.registry, now=self.now)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
