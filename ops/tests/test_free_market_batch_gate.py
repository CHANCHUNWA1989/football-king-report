"""No-network regression tests for free-market candidate quote batches."""
import unittest
from datetime import datetime, timedelta, timezone
from ops.free_market_batch_gate import validate_batch


class FreeMarketBatchGateTests(unittest.TestCase):
    def setUp(self):
        now = datetime(2026, 10, 24, 10, tzinfo=timezone.utc)
        self.capture = now.isoformat()
        self.quote = {
            "market": "totals", "fixture_id": "fixture-1", "source": "offline-fixture",
            "line": 2.5, "outcomes": {"Over": 1.91, "Under": 1.95},
            "updated_at": (now - timedelta(minutes=5)).isoformat(),
            "kickoff_at": (now + timedelta(hours=2)).isoformat(),
        }

    def test_empty_batch_is_hold(self):
        self.assertEqual(validate_batch([], captured_at=self.capture)["status"], "HOLD")

    def test_valid_batch_remains_schema_only(self):
        result = validate_batch([self.quote], captured_at=self.capture)
        self.assertEqual(result["status"], "SCHEMA_VALID_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_duplicate_market_line_is_hold(self):
        result = validate_batch([self.quote, dict(self.quote)], captured_at=self.capture)
        self.assertEqual(result["reason"], "DUPLICATE_MARKET_LINE")

    def test_bad_quote_rejects_entire_batch(self):
        invalid = dict(self.quote, line=2.3)
        self.assertEqual(validate_batch([self.quote, invalid], captured_at=self.capture)["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
