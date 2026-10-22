"""Boundary regressions for market freshness and pre-match event gating."""
import copy
import unittest
from datetime import timedelta

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanTimeBoundaries(unittest.TestCase):
    def test_exactly_eight_hours_old_quote_is_accepted(self):
        event = fixture()
        for book in event["bookmakers"]:
            book["markets"][0]["last_update"] = (NOW - timedelta(hours=8)).isoformat()
        report = aggregate(event, now=NOW)
        self.assertIsNotNone(report)
        self.assertEqual(report["market_last_update_utc"],
                         (NOW - timedelta(hours=8)).isoformat())

    def test_one_second_beyond_eight_hours_rejected(self):
        event = fixture()
        for book in event["bookmakers"]:
            book["markets"][0]["last_update"] = (
                NOW - timedelta(hours=8, seconds=1)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))

    def test_future_market_quote_five_minute_boundary(self):
        event = fixture()
        for book in event["bookmakers"]:
            book["markets"][0]["last_update"] = (
                NOW + timedelta(minutes=5)).isoformat()
        self.assertIsNotNone(aggregate(event, now=NOW))
        for book in event["bookmakers"]:
            book["markets"][0]["last_update"] = (
                NOW + timedelta(minutes=5, seconds=1)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))

    def test_kickoff_ten_minute_boundary(self):
        event = fixture()
        event["commence_time"] = (NOW + timedelta(minutes=10)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))
        event["commence_time"] = (NOW + timedelta(minutes=10, seconds=1)).isoformat()
        self.assertIsNotNone(aggregate(event, now=NOW))

    def test_kickoff_twenty_one_day_boundary(self):
        event = fixture()
        event["commence_time"] = (NOW + timedelta(days=21)).isoformat()
        self.assertIsNotNone(aggregate(event, now=NOW))
        event["commence_time"] = (NOW + timedelta(days=21, seconds=1)).isoformat()
        self.assertIsNone(aggregate(event, now=NOW))


if __name__ == "__main__":
    unittest.main()
