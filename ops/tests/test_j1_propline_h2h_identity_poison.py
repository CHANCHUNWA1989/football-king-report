"""Red/green adversarial J1 PropLine h2h source consistency checks.

All odds are synthetic and are not current or executable prices. No network.
"""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from japan_free_market import SPORT, prop_line


NOW = datetime(2026, 11, 23, 2, 0, tzinfo=timezone.utc)


def synthetic_event():
    books = []
    for key in ("book_a", "book_b"):
        books.append({
            "key": key,
            "markets": [{
                "key": "h2h",
                "last_update": (NOW - timedelta(minutes=1)).isoformat(),
                "outcomes": [
                    {"name": "FC Tokyo", "side": "home", "price_decimal": 2.30},
                    {"name": "Draw", "side": "draw", "price_decimal": 3.20},
                    {"name": "Urawa Reds", "side": "away", "price_decimal": 3.50},
                ],
            }],
        })
    return {
        "id": "fixture-only-123", "sport_key": SPORT,
        "home_team": "FC Tokyo", "away_team": "Urawa Reds",
        "commence_time": (NOW + timedelta(hours=7)).isoformat(),
        "bookmakers": books,
    }


class J1H2HMarketPoisonTests(unittest.TestCase):
    def coverage(self, event):
        return prop_line([event], now=NOW)

    def test_unambiguous_two_books_still_count_as_research_metadata(self):
        state, consensus = self.coverage(synthetic_event())
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(len(consensus), 1)
        self.assertTrue(state["market_quotes_are_not_executable"])
        self.assertEqual(state["production_recommendations"], "DISABLED")

    def test_duplicate_home_with_conflicting_valid_price_poisons_book(self):
        e = synthetic_event()
        e["bookmakers"][0]["markets"][0]["outcomes"].append(
            {"name": "FC Tokyo", "side": "home", "price_decimal": 9.50})
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_duplicate_home_with_invalid_price_still_poisons_book(self):
        e = synthetic_event()
        e["bookmakers"][0]["markets"][0]["outcomes"].append(
            {"name": "FC Tokyo", "side": "home", "price_decimal": "bogus"})
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_two_h2h_market_blocks_for_one_book_poison_book(self):
        e = synthetic_event()
        duplicate = copy.deepcopy(e["bookmakers"][0]["markets"][0])
        duplicate["outcomes"][0]["price_decimal"] = 2.40
        e["bookmakers"][0]["markets"].append(duplicate)
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_bookmaker_without_native_key_cannot_be_second_independent_book(self):
        e = synthetic_event()
        del e["bookmakers"][0]["key"]
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_explicit_home_side_conflicting_with_away_name_poisons_book(self):
        e = synthetic_event()
        e["bookmakers"][0]["markets"][0]["outcomes"][0]["name"] = "Urawa Reds"
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_other_unambiguous_fixture_remains_research_only(self):
        e = synthetic_event()
        e["bookmakers"][0]["markets"][0]["outcomes"][0]["price_decimal"] = 2.20
        state, consensus = self.coverage(e)
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(len(consensus), 1)
        self.assertTrue(state["market_quotes_are_not_executable"])
        self.assertFalse(state["independently_calibrated_j1_model"])


if __name__ == "__main__":
    unittest.main()
