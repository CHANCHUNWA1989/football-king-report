"""End-to-end collect quota safety tests with mocked provider transport.

These tests exercise the real collector, never access a network or consume credits.
"""
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanCollectorQuota(unittest.TestCase):
    def test_low_quota_never_requests_billable_odds(self):
        calls = []
        def fake_retrieve(path, key, **kwargs):
            calls.append(path)
            if path == "/sports/":
                return [{"key": "soccer_epl", "active": True}], {
                    "used": 359, "remaining": 141, "last": 0}
            raise AssertionError("BILLABLE_ENDPOINT_CALLED")
        with patch("ops.odds_market.retrieve", side_effect=fake_retrieve):
            report = collect("dummy-key", now=NOW)
        self.assertEqual(calls, ["/sports/"])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "FREE_QUOTA_GUARD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_quota_headers_never_requests_billable_odds(self):
        calls = []
        def fake_retrieve(path, key, **kwargs):
            calls.append(path)
            return [{"key": "soccer_epl", "active": True}], {
                "used": None, "remaining": None, "last": None}
        with patch("ops.odds_market.retrieve", side_effect=fake_retrieve):
            report = collect("dummy-key", now=NOW)
        self.assertEqual(calls, ["/sports/"])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_repeated_event_id_is_excluded_end_to_end(self):
        calls = []
        def fake_retrieve(path, key, **kwargs):
            calls.append(path)
            if path == "/sports/":
                return [{"key": "soccer_epl", "active": True}], {
                    "used": 0, "remaining": 500, "last": 0}
            if path == "/sports/soccer_epl/odds/":
                event = fixture()
                event["sport_key"] = "soccer_epl"
                return [event, event.copy()], {
                    "used": 1, "remaining": 499, "last": 1}
            raise AssertionError("UNEXPECTED_REQUEST")
        with patch("ops.odds_market.retrieve", side_effect=fake_retrieve):
            report = collect("dummy-key", now=NOW)
        self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
