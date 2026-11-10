"""Reject conflicting duplicate h2h markets from the same bookmaker."""
import copy
import unittest

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanDuplicateMarkets(unittest.TestCase):
    def test_conflicting_second_h2h_market_is_not_selected(self):
        event = fixture()
        duplicate = copy.deepcopy(event["bookmakers"][0]["markets"][0])
        duplicate["outcomes"][0]["price"] = 1.4
        event["bookmakers"][0]["markets"].append(duplicate)
        self.assertIsNone(aggregate(event, now=NOW))

    def test_identical_duplicate_h2h_market_is_also_ambiguous(self):
        event = fixture()
        event["bookmakers"][0]["markets"].append(
            copy.deepcopy(event["bookmakers"][0]["markets"][0]))
        self.assertIsNone(aggregate(event, now=NOW))

    def test_non_h2h_market_does_not_invalidate_unique_h2h(self):
        event = fixture()
        baseline = aggregate(event, now=NOW)
        self.assertIsNotNone(baseline)
        event["bookmakers"][0]["markets"].append({
            "key": "totals", "outcomes": [], "last_update": NOW.isoformat()})
        self.assertEqual(aggregate(event, now=NOW), baseline)


if __name__ == "__main__":
    unittest.main()
