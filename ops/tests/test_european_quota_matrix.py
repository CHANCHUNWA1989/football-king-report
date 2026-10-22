"""Adversarial quota counter matrix for the full collector, offline."""
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW


class TestEuropeanQuotaMatrix(unittest.TestCase):
    def test_paid_response_remaining_counter_invalid(self):
        for bad in (None, "499", True, -1, [], {}, 1.5):
            with self.subTest(bad=repr(bad)):
                calls = []
                def provider(path, key, **kwargs):
                    calls.append(path)
                    if path == "/sports/":
                        return [{"key": "soccer_epl", "active": True},
                                {"key": "soccer_efl_champ", "active": True}], {
                                    "used": 0, "remaining": 500, "last": 0}
                    if path == "/sports/soccer_epl/odds/":
                        return [], {"used": 1, "remaining": bad, "last": 1}
                    raise AssertionError("EXTRA_BILLABLE_REQUEST")
                with patch("ops.odds_market.retrieve", side_effect=provider):
                    result = collect("dummy", now=NOW)
                self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
                self.assertEqual(result["leagues"][0]["status"], "MISSING_QUOTA_HEADERS")
                self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_exact_quota_boundaries(self):
        cases = [(359, 142, True), (360, 142, False),
                 (359, 141, False), (359, 140, False)]
        for used, remaining, should_query in cases:
            with self.subTest(used=used, remaining=remaining):
                calls = []
                def provider(path, key, **kwargs):
                    calls.append(path)
                    if path == "/sports/":
                        return [{"key": "soccer_epl", "active": True}], {
                            "used": used, "remaining": remaining, "last": 0}
                    if path == "/sports/soccer_epl/odds/":
                        return [], {"used": 360, "remaining": 140, "last": 1}
                    raise AssertionError("UNEXPECTED_REQUEST")
                with patch("ops.odds_market.retrieve", side_effect=provider):
                    result = collect("dummy", now=NOW)
                self.assertEqual(len(calls) == 2, should_query)
                self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
