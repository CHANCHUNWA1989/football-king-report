"""Prevent malformed duplicate bookmaker records bypassing consensus isolation."""
import copy
import unittest

from ops.odds_market import aggregate
from ops.tests.test_european_market_stress import NOW, fixture


class TestEuropeanDuplicateBookmakerBypass(unittest.TestCase):
    def test_invalid_then_valid_duplicate_key_is_rejected(self):
        event = fixture()
        bad = copy.deepcopy(event["bookmakers"][0])
        bad["markets"] = []
        event["bookmakers"].insert(0, bad)
        self.assertIsNone(aggregate(event, now=NOW))

    def test_valid_then_invalid_duplicate_key_is_rejected(self):
        event = fixture()
        bad = copy.deepcopy(event["bookmakers"][0])
        bad["markets"] = []
        event["bookmakers"].append(bad)
        self.assertIsNone(aggregate(event, now=NOW))

    def test_three_unique_valid_bookmakers_survive_one_duplicate(self):
        event = fixture()
        third = copy.deepcopy(event["bookmakers"][0])
        third["key"] = "third-independent-book"
        bad = copy.deepcopy(event["bookmakers"][0])
        bad["markets"] = []
        event["bookmakers"].extend([third, bad])
        result = aggregate(event, now=NOW)
        self.assertIsNotNone(result)
        self.assertEqual(result["contributing_bookmakers"], 2)
        self.assertFalse(result["prediction_or_value_bet"])


if __name__ == "__main__":
    unittest.main()
