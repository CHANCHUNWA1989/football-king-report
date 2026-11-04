"""1X2 market freshness and adversarial bookmaker tests (offline)."""
import copy
import unittest
from datetime import timedelta

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanMarketIntegrity(unittest.TestCase):
    def test_oldest_bookmaker_controls_market_freshness(self):
        event = fixture()
        event["bookmakers"][1]["markets"][0]["last_update"] = (
            NOW - timedelta(hours=7, minutes=59)).isoformat()
        report = aggregate(event, now=NOW)
        self.assertIsNotNone(report)
        self.assertEqual(report["market_last_update_utc"],
                         (NOW - timedelta(hours=7, minutes=59)).isoformat())

    def test_one_bookmaker_cannot_manufacture_consensus(self):
        event = fixture()
        event["bookmakers"] = event["bookmakers"][:1]
        self.assertIsNone(aggregate(event, now=NOW))

    def test_duplicate_bookmaker_with_conflicting_price_rejected(self):
        event = fixture()
        duplicate = copy.deepcopy(event["bookmakers"][0])
        duplicate["markets"][0]["outcomes"][0]["price"] = 2.8
        event["bookmakers"].append(duplicate)
        self.assertIsNone(aggregate(event, now=NOW))

    def test_future_timestamp_and_invalid_overround_rejected(self):
        event = fixture()
        event["bookmakers"][0]["markets"][0]["last_update"] = (
            NOW + timedelta(minutes=6)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))
        event = fixture()
        for book in event["bookmakers"]:
            for outcome in book["markets"][0]["outcomes"]:
                outcome["price"] = 1.1
        self.assertIsNone(aggregate(event, now=NOW))

    def test_stale_quote_cannot_be_replaced_by_book_timestamp(self):
        event = fixture()
        event["bookmakers"][0]["last_update"] = NOW.isoformat()
        event["bookmakers"][0]["markets"][0]["last_update"] = (
            NOW - timedelta(hours=9)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))


if __name__ == "__main__":
    unittest.main()
