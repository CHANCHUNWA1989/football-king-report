"""Batch-size, duplicate-ID and output privacy stress for 1X2 collector.

Uses the production collect/aggregate code with mocked provider responses.
No network calls, credentials, or billable API requests.
"""
import copy
import unittest
from unittest.mock import patch

from ops.odds_market import collect
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanCollectorBatchStress(unittest.TestCase):
    def run_batch(self, matches):
        calls = []
        def provider(path, key, **kwargs):
            calls.append(path)
            if path == "/sports/":
                return [{"key": "soccer_epl", "active": True}], {
                    "used": 0, "remaining": 500, "last": 0}
            if path == "/sports/soccer_epl/odds/":
                return matches, {"used": 1, "remaining": 499, "last": 1}
            raise AssertionError("UNEXPECTED_BILLABLE_REQUEST")
        with patch("ops.odds_market.retrieve", side_effect=provider):
            report = collect("dummy", now=NOW)
        self.assertEqual(calls, ["/sports/", "/sports/soccer_epl/odds/"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        return report

    def test_2000_events_truncated_to_500(self):
        base = fixture()
        base["sport_key"] = "soccer_epl"
        events = []
        for i in range(2000):
            row = copy.deepcopy(base)
            row["id"] = "event-" + str(i)
            events.append(row)
        report = self.run_batch(events)
        self.assertEqual(report["event_count"], 500)
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(len({x["source_event_id"] for x in report["events"]}), 500)
        self.assertTrue(all(x["prediction_or_value_bet"] is False for x in report["events"]))

    def test_duplicate_flood_does_not_create_fake_independent_events(self):
        base = fixture()
        base["sport_key"] = "soccer_epl"
        report = self.run_batch([copy.deepcopy(base) for _ in range(500)])
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["status"], "HOLD")

    def test_derived_output_excludes_raw_bookmaker_prices(self):
        base = fixture()
        base["sport_key"] = "soccer_epl"
        report = self.run_batch([base])
        self.assertEqual(report["event_count"], 1)
        row = report["events"][0]
        self.assertFalse(any(k in row for k in ("bookmakers", "outcomes", "price", "odds")))
        self.assertFalse(report["raw_bookmaker_quotes_redistributed"])
        self.assertFalse(report["raw_bookmaker_names_redistributed"])


if __name__ == "__main__":
    unittest.main()
