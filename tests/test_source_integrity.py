"""Offline regression tests for multi-source quote integrity."""
import unittest
from ops.source_integrity import audit_quotes


def quote(source="alpha", **changes):
    row = {"source": source, "event_id": "fixture-1", "home_id": "home",
           "away_id": "away", "kickoff_utc": "2026-10-20T16:00:00+08:00",
           "quoted_at_utc": "2026-10-20T14:50:00+08:00",
           "market": "h2h", "selection": "home", "decimal_odds": 2.1}
    row.update(changes)
    return row


NOW = "2026-10-20T15:00:00+08:00"


class SourceIntegrityTests(unittest.TestCase):
    def test_matching_quotes_still_hold(self):
        result = audit_quotes([quote(), quote("beta")], now_utc=NOW)
        self.assertEqual(result["verified_count"], 2)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_kickoff_conflict(self):
        result = audit_quotes([quote(), quote("beta", kickoff_utc="2026-10-20T17:00:00+08:00")], now_utc=NOW)
        self.assertEqual(result["reason"], "FIXTURE_OR_MARKET_CONFLICT")

    def test_wrong_market(self):
        result = audit_quotes([quote(), quote("beta", selection="away")], now_utc=NOW)
        self.assertEqual(result["reason"], "FIXTURE_OR_MARKET_CONFLICT")

    def test_same_source(self):
        result = audit_quotes([quote(), quote()], now_utc=NOW)
        self.assertEqual(result["reason"], "DUPLICATE_SOURCE")

    def test_stale(self):
        result = audit_quotes([quote(quoted_at_utc="2026-10-20T13:00:00+08:00"), quote("beta")], now_utc=NOW)
        self.assertEqual(result["reason"], "INSUFFICIENT_VALID_QUOTES")

    def test_naive_timestamp(self):
        result = audit_quotes([quote(quoted_at_utc="2026-10-20T14:50:00"), quote("beta")], now_utc=NOW)
        self.assertEqual(result["reason"], "INSUFFICIENT_VALID_QUOTES")

    def test_in_play(self):
        result = audit_quotes([quote(), quote("beta")], now_utc="2026-10-20T16:01:00+08:00")
        self.assertEqual(result["reason"], "INSUFFICIENT_VALID_QUOTES")

    def test_invalid_odds(self):
        result = audit_quotes([quote(decimal_odds=True), quote("beta")], now_utc=NOW)
        self.assertEqual(result["reason"], "INSUFFICIENT_VALID_QUOTES")


if __name__ == "__main__":
    unittest.main()
