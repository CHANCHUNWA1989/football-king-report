"""Quota circuit-breaker end-to-end regression under multi-league collection."""
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanQuotaCircuitBreaker(unittest.TestCase):
    def test_provider_quota_drop_stops_remaining_leagues(self):
        calls = []
        def provider(path, key, **kwargs):
            calls.append(path)
            if path == "/sports/":
                return [
                    {"key": "soccer_epl", "active": True},
                    {"key": "soccer_efl_champ", "active": True},
                    {"key": "soccer_germany_bundesliga", "active": True},
                ], {"used": 0, "remaining": 500, "last": 0}
            if path == "/sports/soccer_epl/odds/":
                event = fixture()
                event["sport_key"] = "soccer_epl"
                return [event], {"used": 360, "remaining": 140, "last": 1}
            raise AssertionError("CIRCUIT_BREAKER_DID_NOT_STOP")
        with patch("ops.odds_market.retrieve", side_effect=provider):
            report = collect("dummy", now=NOW)
        self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
        self.assertEqual(report["event_count"], 1)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertTrue(any(x["status"] == "QUOTA_GUARD" for x in report["leagues"]))

    def test_missing_quota_after_paid_request_stops_remaining_leagues(self):
        calls = []
        def provider(path, key, **kwargs):
            calls.append(path)
            if path == "/sports/":
                return [{"key": "soccer_epl", "active": True},
                        {"key": "soccer_efl_champ", "active": True}], {
                            "used": 0, "remaining": 500, "last": 0}
            if path == "/sports/soccer_epl/odds/":
                return [], {"used": None, "remaining": None, "last": None}
            raise AssertionError("MISSING_QUOTA_MUST_STOP")
        with patch("ops.odds_market.retrieve", side_effect=provider):
            report = collect("dummy", now=NOW)
        self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
        self.assertEqual(report["event_count"], 0)
        self.assertTrue(any(x["status"] == "MISSING_QUOTA_HEADERS" for x in report["leagues"]))
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
