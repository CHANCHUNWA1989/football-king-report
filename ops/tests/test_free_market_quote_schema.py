"""Offline tests: no network calls and no provider credits."""
import unittest
from datetime import datetime, timedelta, timezone
from ops.free_market_quote_schema import validate_quote


class FreeMarketQuoteSchemaTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
        self.quote = {
            "market": "totals", "fixture_id": "fixture-1", "source": "offline-fixture",
            "line": 2.5, "outcomes": {"Over": 1.91, "Under": 1.95},
            "updated_at": (self.now - timedelta(minutes=5)).isoformat(),
            "kickoff_at": (self.now + timedelta(hours=2)).isoformat(),
        }

    def test_valid_total_is_only_schema_valid(self):
        result = validate_quote(self.quote, captured_at=self.now.isoformat())
        self.assertEqual(result["status"], "SCHEMA_VALID_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_valid_handicap(self):
        self.quote.update(market="spreads", line=-0.25,
                          outcomes={"Home": 1.90, "Away": 1.96})
        self.assertEqual(validate_quote(self.quote, captured_at=self.now.isoformat())["market"], "spreads")

    def test_invalid_line(self):
        self.quote["line"] = 2.3
        with self.assertRaises(ValueError):
            validate_quote(self.quote, captured_at=self.now.isoformat())

    def test_missing_outcome(self):
        self.quote["outcomes"] = {"Over": 1.91}
        with self.assertRaises(ValueError):
            validate_quote(self.quote, captured_at=self.now.isoformat())

    def test_stale_quote(self):
        self.quote["updated_at"] = (self.now - timedelta(hours=1)).isoformat()
        with self.assertRaises(ValueError):
            validate_quote(self.quote, captured_at=self.now.isoformat())

    def test_started_fixture(self):
        self.quote["kickoff_at"] = (self.now - timedelta(minutes=1)).isoformat()
        with self.assertRaises(ValueError):
            validate_quote(self.quote, captured_at=self.now.isoformat())


if __name__ == "__main__":
    unittest.main()
