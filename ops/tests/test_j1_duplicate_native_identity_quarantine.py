"""Test-first J1 native event and bookmaker duplicate quarantine.

All fixture IDs, bookmaker keys and 1X2 prices are synthetic research data.
No provider network, API keys, wagers, model scores or live claims.
"""
import copy
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from japan_free_market import prop_line
from test_j1_propline_h2h_identity_poison import NOW, synthetic_event


def check(events):
    return prop_line(events, now=NOW)


class J1DuplicateNativeIdentityQuarantineTests(unittest.TestCase):
    def test_single_unambiguous_fixture_and_two_books_still_covered(self):
        row = synthetic_event()
        state, consensus = check([row])
        self.assertEqual(state["upcoming_events"], 1)
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(len(consensus), 1)
        self.assertEqual(state["production_recommendations"], "DISABLED")
        self.assertTrue(state["market_quotes_are_not_executable"])

    def test_same_native_event_id_repeated_exactly_rejected_in_all_copies(self):
        row = synthetic_event()
        state, consensus = check([row, copy.deepcopy(row)])
        self.assertEqual(state["upcoming_events"], 0)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_same_native_event_id_conflicting_second_price_rejected(self):
        first = synthetic_event()
        second = copy.deepcopy(first)
        second["bookmakers"][0]["markets"][0]["outcomes"][0]["price_decimal"] = 8.5
        state, consensus = check([first, second])
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_numeric_string_event_id_collision_rejected(self):
        first = synthetic_event()
        second = copy.deepcopy(first)
        first["id"] = 321
        second["id"] = "321"
        state, consensus = check([first, second])
        self.assertEqual(state["upcoming_events"], 0)
        self.assertEqual(consensus, {})

    def test_second_duplicate_event_marked_completed_still_quarantines_first(self):
        first = synthetic_event()
        second = copy.deepcopy(first)
        second["completed"] = True
        state, consensus = check([first, second])
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_distinct_native_ids_same_team_and_kickoff_not_double_counted(self):
        first = synthetic_event()
        second = copy.deepcopy(first)
        second["id"] = "alternative-publisher-id-for-same-event"
        state, consensus = check([first, second])
        self.assertEqual(state["upcoming_events"], 0)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_duplicate_bookmaker_key_with_conflicting_quote_poisons_book(self):
        row = synthetic_event()
        repeated = copy.deepcopy(row["bookmakers"][0])
        repeated["markets"][0]["outcomes"][0]["price_decimal"] = 7.7
        row["bookmakers"].append(repeated)
        state, consensus = check([row])
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_duplicate_bookmaker_even_with_invalid_second_block_is_poisoned(self):
        row = synthetic_event()
        row["bookmakers"].append({"key": "book_a", "markets": []})
        state, consensus = check([row])
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_duplicate_bookmaker_with_invalid_first_block_is_poisoned(self):
        row = synthetic_event()
        row["bookmakers"].insert(0, {"key": "book_a", "markets": "invalid"})
        state, consensus = check([row])
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})

    def test_healthy_third_book_keeps_coverage_when_duplicate_book_quarantined(self):
        row = synthetic_event()
        row["bookmakers"].append(copy.deepcopy(row["bookmakers"][0]))
        third = copy.deepcopy(row["bookmakers"][1])
        third["key"] = "book_c"
        row["bookmakers"].append(third)
        state, consensus = check([row])
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(len(consensus), 1)

    def test_duplicate_fixture_does_not_poison_different_kickoff_fixture(self):
        first = synthetic_event()
        duplicated = copy.deepcopy(first)
        other = copy.deepcopy(first)
        other["id"] = "independent-native-j1-fixture-2"
        from datetime import datetime
        other["commence_time"] = (
            datetime.fromisoformat(first["commence_time"]) + timedelta(hours=2)
        ).isoformat()
        state, consensus = check([first, duplicated, other])
        self.assertEqual(state["upcoming_events"], 1)
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(len(consensus), 1)

    def test_bool_event_id_is_not_a_native_fixture_id(self):
        row = synthetic_event()
        row["id"] = True
        state, consensus = check([row])
        self.assertEqual(state["upcoming_events"], 0)
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(consensus, {})


if __name__ == "__main__":
    unittest.main()
