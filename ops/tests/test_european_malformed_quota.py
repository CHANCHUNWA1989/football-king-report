"""Fail-closed collector regressions for malformed provider quota counters."""
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW


class TestEuropeanMalformedQuota(unittest.TestCase):
    def test_malformed_paid_response_counters_stop_other_leagues(self):
        for invalid in (None, [], "500", True, -1, 3.5):
            with self.subTest(invalid=repr(invalid)):
                calls = []
                def provider(path, key, **kwargs):
                    calls.append(path)
                    if path == "/sports/":
                        return [{"key": "soccer_epl", "active": True},
                                {"key": "soccer_efl_champ", "active": True}], {
                                    "used": 0, "remaining": 500, "last": 0}
                    if path == "/sports/soccer_epl/odds/":
                        return [], {"used": invalid, "remaining": 499, "last": 1}
                    raise AssertionError("MUST_NOT_QUERY_NEXT_LEAGUE")
                with patch("ops.odds_market.retrieve", side_effect=provider):
                    result = collect("dummy", now=NOW)
                self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
                self.assertEqual(result["event_count"], 0)
                self.assertEqual(result["leagues"][0]["status"], "MISSING_QUOTA_HEADERS")
                self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
