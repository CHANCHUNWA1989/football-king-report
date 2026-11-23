"""Test-first PropLine J1 paired spread/total coverage integrity.

All odds, lines, fixtures and market timestamps in this file are synthetic.
Do not infer bookmaker execution, live prices, EV or prospective performance.
"""
import copy
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from japan_free_market import prop_line
from test_j1_propline_h2h_identity_poison import NOW, synthetic_event


def spread(home=-0.25, away=0.25):
    return {
        "key":"spreads","last_update":(NOW-timedelta(minutes=1)).isoformat(),
        "outcomes":[
            {"name":"FC Tokyo","side":"home","point":home,"price_decimal":1.91},
            {"name":"Urawa Reds","side":"away","point":away,"price_decimal":1.95},
        ],
    }


def total(over=2.5, under=2.5):
    return {
        "key":"totals","last_update":(NOW-timedelta(minutes=1)).isoformat(),
        "outcomes":[
            {"name":"Over","point":over,"price_decimal":1.93},
            {"name":"Under","point":under,"price_decimal":1.94},
        ],
    }


def fixture_with_lines():
    e=synthetic_event()
    for book in e["bookmakers"]:
        book["markets"].extend((spread(),total()))
    return e


def snapshot(e):
    state,consensus=prop_line([e],now=NOW)
    assert state["market_quotes_are_not_executable"] is True
    assert state["production_recommendations"]=="DISABLED"
    return state,consensus


class J1ProplineTwoWayLineCoverageTests(unittest.TestCase):
    def test_complete_spread_and_total_each_count_research_coverage(self):
        s,c=snapshot(fixture_with_lines())
        self.assertEqual(s["fresh_spread_event_count"],1)
        self.assertEqual(s["fresh_totals_event_count"],1)
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(len(c),1)

    def test_only_one_home_spread_leg_not_a_market(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["outcomes"]=book["markets"][1]["outcomes"][:1]
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)

    def test_only_one_over_total_leg_not_a_market(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][2]["outcomes"]=book["markets"][2]["outcomes"][:1]
        s,_=snapshot(e)
        self.assertEqual(s["fresh_totals_event_count"],0)

    def test_spread_both_outcomes_must_have_equal_opposite_lines(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["outcomes"][1]["point"]=0.5
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)

    def test_total_over_under_must_share_exact_goal_line(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][2]["outcomes"][1]["point"]=3.5
        s,_=snapshot(e)
        self.assertEqual(s["fresh_totals_event_count"],0)

    def test_duplicate_same_side_spread_poisoned_even_with_valid_pair(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["outcomes"].append(
                {"name":"FC Tokyo","side":"home","point":-0.25,"price_decimal":1.88})
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)

    def test_duplicate_over_total_poisoned_even_with_valid_pair(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][2]["outcomes"].append(
                {"name":"Over","point":2.5,"price_decimal":2.02})
        s,_=snapshot(e)
        self.assertEqual(s["fresh_totals_event_count"],0)

    def test_spread_invalid_price_on_away_leg_poisoned(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["outcomes"][1]["price_decimal"]=True
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)

    def test_total_non_quarter_goal_line_poisoned(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][2]["outcomes"][1]["point"]=2.6
        s,_=snapshot(e)
        self.assertEqual(s["fresh_totals_event_count"],0)

    def test_two_spread_market_blocks_in_one_book_poison_that_book(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"].append(copy.deepcopy(book["markets"][1]))
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)

    def test_two_total_market_blocks_in_one_book_poison_that_book(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"].append(copy.deepcopy(book["markets"][2]))
        s,_=snapshot(e)
        self.assertEqual(s["fresh_totals_event_count"],0)

    def test_one_complete_book_still_counts_coverage_not_execution(self):
        e=fixture_with_lines()
        e["bookmakers"][1]["markets"][1]["outcomes"]=[]
        e["bookmakers"][1]["markets"][2]["outcomes"]=[]
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],1)
        self.assertEqual(s["fresh_totals_event_count"],1)
        self.assertTrue(s["market_quotes_are_not_executable"])

    def test_other_healthy_total_survives_bad_spread(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["outcomes"]=[]
        s,c=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)
        self.assertEqual(s["fresh_totals_event_count"],1)
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(len(c),1)

    def test_suspended_complete_market_does_not_count(self):
        e=fixture_with_lines()
        for book in e["bookmakers"]:
            book["markets"][1]["suspended_at"]=NOW.isoformat()
            book["markets"][2]["suspended_at"]=NOW.isoformat()
        s,_=snapshot(e)
        self.assertEqual(s["fresh_spread_event_count"],0)
        self.assertEqual(s["fresh_totals_event_count"],0)


if __name__=="__main__":
    unittest.main()
