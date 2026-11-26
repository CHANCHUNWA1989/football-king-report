"""Synthetic settlement and same-line comparison checks."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_market_share import effective_share, compare
from test_deep_handicap_private_capture import inputs, NOW


def pair():
    s,q=inputs()
    for item in copy.deepcopy(q["quotes"]):
        item["bookmaker"]="synthetic-second-book"
        q["quotes"].append(item)
    q["quotes_accepted"]=4
    return s,q


class MarketShareTests(unittest.TestCase):
    def test_half_stake_and_push_math(self):
        p=dict(FULL_WIN=.2,HALF_WIN=.2,PUSH=.1,HALF_LOSS=.2,FULL_LOSS=.3)
        self.assertAlmostEqual(effective_share(p),3/7)
        self.assertNotEqual(effective_share(p),p["FULL_WIN"])
        with self.assertRaises(ValueError):
            effective_share(dict(FULL_WIN=0,HALF_WIN=0,PUSH=1,HALF_LOSS=0,FULL_LOSS=0))

    def test_two_complete_books_private_only(self):
        s,q=pair()
        before=copy.deepcopy((s,q))
        r=compare(s,q,now=NOW)
        self.assertEqual((s,q),before)
        self.assertEqual(r["book_pair_count"],2)
        self.assertAlmostEqual(r["private_diagnostics"]["normalized_inverse_price_share_median"],.5)
        for model in r["private_diagnostics"]["models"].values():
            self.assertAlmostEqual(model["share_minus_market_proxy"],
                                   model["settlement_weighted_share"]-.5)
        self.assertFalse(r["market_bias_verified"])
        self.assertFalse(r["qualifies_for_betting"])
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertNotIn("synthetic-private-book",json.dumps(r))
        self.assertNotIn("decimal_odds",json.dumps(r))

    def test_bad_or_incomplete_market_returns_no_partial_metrics(self):
        s,q=inputs()
        self.assertIsNone(compare(s,q,now=NOW)["private_diagnostics"])
        for change in (
            lambda q:q["quotes"][2].update(point=-2),
            lambda q:q["quotes"][2].update(decimal_odds=10),
            lambda q:q["quotes"][2].update(decimal_odds=1.01),
            lambda q:q["quotes"][2].update(bookmaker=q["quotes"][0]["bookmaker"]),
            lambda q:q["quotes"][2].update(market_last_update_utc="2026-11-27T07:50:00Z"),
        ):
            s,q=pair()
            change(q)
            self.assertIsNone(compare(s,q,now=NOW)["private_diagnostics"])

    def test_price_order_permutation_does_not_change_metrics(self):
        s,q=pair()
        q["quotes"][0]["decimal_odds"]=1.8
        a=compare(s,q,now=NOW)["private_diagnostics"]
        q["quotes"].reverse()
        b=compare(s,q,now=NOW)["private_diagnostics"]
        self.assertIsNotNone(a)
        self.assertEqual(a,b)
