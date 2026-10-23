"""Synthetic, zero-network regression tests for live quote gate."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_quote_gate import assess_quote


class TestLiveQuoteGate(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 23, 10, 0, tzinfo=timezone.utc)
        self.quote = {
            "source_event_id": "event-1",
            "bookmaker": "licensed-example",
            "market": "totals",
            "selection": "over_2.5",
            "market_last_update_utc": self.now.isoformat(),
            "decimal_odds": 1.92,
            "source_authorized": True,
            "is_live": True,
        }

    def status(self, quote, **kwargs):
        return assess_quote(quote, now=self.now, live=True, **kwargs)["status"]

    def test_fresh_quote_is_research_only(self):
        self.assertEqual(self.status(self.quote), "RESEARCH_ONLY")

    def test_consensus_never_becomes_executable(self):
        q = {**self.quote, "probabilities_are_no_vig_consensus": True}
        self.assertEqual(self.status(q), "HOLD")

    def test_live_flag_required(self):
        self.assertEqual(self.status({**self.quote, "is_live": False}), "HOLD")

    def test_source_identity_required(self):
        for key in ("source_event_id", "bookmaker", "market", "selection"):
            with self.subTest(key=key):
                self.assertEqual(self.status({**self.quote, key: ""}), "HOLD")

    def test_timestamp_must_be_tz_aware_and_fresh(self):
        for value in ("2026-10-23T10:00:00", "not-a-time", None):
            with self.subTest(value=value):
                self.assertEqual(self.status({**self.quote, "market_last_update_utc": value}), "HOLD")
        old = (self.now - timedelta(seconds=121)).isoformat()
        self.assertEqual(self.status({**self.quote, "market_last_update_utc": old}), "HOLD")
        future = (self.now + timedelta(seconds=31)).isoformat()
        self.assertEqual(self.status({**self.quote, "market_last_update_utc": future}), "HOLD")

    def test_invalid_odds_fail_closed(self):
        for value in (None, True, 1.0, 501, "1.92", float("nan")):
            with self.subTest(value=repr(value)):
                self.assertEqual(self.status({**self.quote, "decimal_odds": value}), "HOLD")

    def test_authorization_required(self):
        self.assertEqual(self.status({**self.quote, "source_authorized": False}), "HOLD")

    def test_invalid_quote_shape(self):
        for value in (None, [], "text"):
            self.assertEqual(self.status(value), "HOLD")


if __name__ == "__main__":
    unittest.main()
