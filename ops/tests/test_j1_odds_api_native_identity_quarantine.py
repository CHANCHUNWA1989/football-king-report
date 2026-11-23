"""Test-first: J1 The Odds API native fixture/bookmaker quarantine.

Every market price here is synthetic; both provider HTTP calls are mocked.
This suite does NOT prove an authenticated or executable bookmaker quote.
"""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import japan_free_market as jfm


NOW = datetime(2026, 11, 23, 3, 0, tzinfo=timezone.utc)


def event():
    books=[]
    for native_key, prices in (
        ("book_one", (2.30, 3.20, 3.40)),
        ("book_two", (2.35, 3.25, 3.30)),
    ):
        books.append({
            "key": native_key,
            "markets": [{
                "key": "h2h",
                "last_update": (NOW-timedelta(minutes=2)).isoformat(),
                "outcomes": [
                    {"name": "FC Tokyo", "price": prices[0]},
                    {"name": "Draw", "price": prices[1]},
                    {"name": "Urawa Reds", "price": prices[2]},
                ],
            }],
        })
    return {
        "id": "native-odds-j1-999", "sport_key": jfm.SPORT,
        "home_team": "FC Tokyo", "away_team": "Urawa Reds",
        "commence_time": (NOW+timedelta(hours=7)).isoformat(),
        "bookmakers": books,
    }


def simulated_feed(rows):
    """TWO mocked responses; never calls a provider or reads a secret."""
    visited=[]
    def fake_retrieve(path, _key, *, opener=None, params=None):
        visited.append((path, params))
        if path==jfm.THE_ODDS_SPORTS:
            return [{"key": jfm.SPORT, "active": True}], {"used": 50, "remaining": 450}
        if path==jfm.THE_ODDS_J1:
            return copy.deepcopy(rows), {"used": 51, "remaining": 449}
        raise AssertionError("UNEXPECTED_PROVIDER_ENDPOINT")
    with patch.object(jfm, "odds_retrieve", side_effect=fake_retrieve):
        state, consensus=jfm.odds_japan("synthetic-token-not-real",now=NOW,opener=lambda *a: None)
    assert len(visited)==2
    assert visited[1][1]["markets"]=="h2h"
    assert state["production_recommendations"]=="DISABLED"
    assert state["market_quotes_are_not_executable"] is True
    assert state["independently_calibrated_j1_model"] is False
    assert "synthetic-token-not-real" not in json.dumps(state)
    assert "book_one" not in json.dumps(state)
    return state,consensus


class J1OddsApiNativeIdentityQuarantineTests(unittest.TestCase):
    def test_valid_two_unique_books_and_native_id_is_research_only(self):
        s,c=simulated_feed([event()])
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(s["upcoming_events"],1)
        self.assertEqual(len(c),1)
        self.assertEqual(s["status"],"RESEARCH_ONLY")

    def test_same_event_id_twice_even_identical_is_quarantined(self):
        e=event()
        s,c=simulated_feed([e,copy.deepcopy(e)])
        self.assertEqual(s["upcoming_events"],0)
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_same_event_id_with_different_quote_is_quarantined(self):
        a=event()
        b=copy.deepcopy(a)
        b["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=5.0
        s,c=simulated_feed([a,b])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_same_event_id_mismatched_kickoff_is_quarantined(self):
        a=event()
        b=copy.deepcopy(a)
        b["commence_time"]=(NOW+timedelta(hours=9)).isoformat()
        s,c=simulated_feed([a,b])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_same_teams_kickoff_two_distinct_native_event_ids_is_quarantined(self):
        a=event()
        b=copy.deepcopy(a)
        b["id"]="different-native-id-same-j1-fixture"
        s,c=simulated_feed([a,b])
        self.assertEqual(s["upcoming_events"],0)
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_completed_duplicate_event_still_poison_all_copies(self):
        a=event()
        b=copy.deepcopy(a)
        b["completed"]=True
        s,c=simulated_feed([a,b])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_bool_or_missing_native_event_id_is_not_research_fixture(self):
        for value in (True,None,"",[],False):
            with self.subTest(value=value):
                e=event()
                if value is None:
                    del e["id"]
                else:
                    e["id"]=value
                s,c=simulated_feed([e])
                self.assertEqual(s["upcoming_events"],0)
                self.assertEqual(c,{})

    def test_duplicate_bookmaker_key_invalid_later_copy_poisons_first(self):
        e=event()
        e["bookmakers"].append({"key":"book_one","markets":"bad"})
        s,c=simulated_feed([e])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_duplicate_bookmaker_key_invalid_earlier_copy_poisons_later(self):
        e=event()
        e["bookmakers"].insert(0,{"key":"book_one","markets":[]})
        s,c=simulated_feed([e])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_duplicate_bookmaker_different_prices_poisons_both(self):
        e=event()
        b=copy.deepcopy(e["bookmakers"][0])
        b["markets"][0]["outcomes"][0]["price"]=6.0
        e["bookmakers"].append(b)
        s,c=simulated_feed([e])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_third_distinct_book_can_keep_valid_research_coverage(self):
        e=event()
        dup=copy.deepcopy(e["bookmakers"][0])
        third=copy.deepcopy(e["bookmakers"][1])
        third["key"]="book_three"
        e["bookmakers"].extend((dup,third))
        s,c=simulated_feed([e])
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(len(c),1)

    def test_duplicate_h2h_market_blocks_in_one_book_poison_book(self):
        e=event()
        b=e["bookmakers"][0]
        b["markets"].append(copy.deepcopy(b["markets"][0]))
        s,c=simulated_feed([e])
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(c,{})

    def test_other_sport_key_cannot_launder_as_j1(self):
        e=event()
        e["sport_key"]="soccer_germany_bundesliga"
        s,c=simulated_feed([e])
        self.assertEqual(s["upcoming_events"],0)
        self.assertEqual(c,{})

    def test_other_distinct_fixture_preserved_with_poisoned_pair(self):
        a=event()
        duplicate=copy.deepcopy(a)
        different=copy.deepcopy(a)
        different["id"]="different-fixture-and-kickoff"
        different["commence_time"]=(NOW+timedelta(hours=9)).isoformat()
        s,c=simulated_feed([a,duplicate,different])
        self.assertEqual(s["upcoming_events"],1)
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(len(c),1)

    def test_independent_two_distinct_fixtures_accepted_as_metadata_only(self):
        a=event()
        b=copy.deepcopy(a)
        b["id"]="different-native-event"
        b["commence_time"]=(NOW+timedelta(hours=9)).isoformat()
        s,c=simulated_feed([a,b])
        self.assertEqual(s["upcoming_events"],2)
        self.assertEqual(s["fresh_3way_event_count"],2)
        self.assertEqual(len(c),2)


if __name__ == "__main__":
    unittest.main()
