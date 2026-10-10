"""Offline, no-credential tests for the FREE six-league quality gate."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from six_league_free_upgrade import (
    LEAGUES, SCHEMA, audit, collect, complete_market, extract, validate,
)

class SixFreeUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 10, 8, tzinfo=timezone.utc)
        self.updated = (self.now-timedelta(minutes=2)).isoformat()
        self.kickoff = (self.now+timedelta(days=1)).isoformat()
        self.league = "epl"
        self.sport = LEAGUES[self.league]
        self.market = {
            "id": "future-epl-1", "sport_key": self.sport,
            "home_team": "Arsenal", "away_team": "Chelsea",
            "commence_time": self.kickoff, "bookmakers": []
        }
        for name in ("book_alpha", "book_beta"):
            self.market["bookmakers"].append({
                "key": name,
                "markets": [
                    {"key": "h2h", "last_update": self.updated, "outcomes": [
                        {"name": "Arsenal", "price_decimal": 2.4},
                        {"name": "Draw", "price_decimal": 3.3},
                        {"name": "Chelsea", "price_decimal": 2.9}]},
                    {"key": "spreads", "last_update": self.updated, "outcomes": [
                        {"name": "Arsenal", "point": -0.25, "price_decimal": 1.91},
                        {"name": "Chelsea", "point": 0.25, "price_decimal": 1.95}]},
                    {"key": "totals", "last_update": self.updated, "outcomes": [
                        {"name": "Over", "point": 2.5, "price_decimal": 1.90},
                        {"name": "Under", "point": 2.5, "price_decimal": 1.97}]},
                ]
            })

    def test_two_sided_main_markets(self):
        s = extract([self.market], self.league, self.sport, self.now)
        self.assertEqual((s["utc_identity_events"], s["full_1x2_events"],
                          s["paired_spread_events"], s["paired_totals_events"]),
                         (1, 1, 1, 1))

    def test_one_sided_spread_must_not_count(self):
        x=copy.deepcopy(self.market)
        for book in x["bookmakers"]:
            book["markets"][1]["outcomes"].pop()
        self.assertEqual(extract([x], self.league, self.sport, self.now)["paired_spread_events"], 0)

    def test_mismatched_handicap_sign_does_not_count(self):
        x=copy.deepcopy(self.market)
        for book in x["bookmakers"]:
            book["markets"][1]["outcomes"][1]["point"] = -0.25
        self.assertEqual(extract([x], self.league, self.sport, self.now)["paired_spread_events"], 0)

    def test_mismatched_total_point_does_not_count(self):
        x=copy.deepcopy(self.market)
        for book in x["bookmakers"]:
            book["markets"][2]["outcomes"][1]["point"] = 3.5
        self.assertEqual(extract([x], self.league, self.sport, self.now)["paired_totals_events"], 0)

    def test_duplicate_bookie_does_not_fake_independence(self):
        x=copy.deepcopy(self.market)
        x["bookmakers"][1]["key"] = "book_alpha"
        s=extract([x], self.league, self.sport, self.now)
        self.assertEqual(s["full_1x2_events"],0)
        self.assertEqual(s["duplicate_book_blocks"],1)

    def test_duplicate_outcome_disqualifies_complete_market(self):
        x=copy.deepcopy(self.market)
        q=x["bookmakers"][0]["markets"][1]
        q["outcomes"].append(copy.deepcopy(q["outcomes"][0]))
        self.assertIsNone(complete_market(q,"Arsenal","Chelsea"))

    def test_stale_and_inplay_cannot_count(self):
        x=copy.deepcopy(self.market)
        for book in x["bookmakers"]:
            for m in book["markets"]:
                m["last_update"] = (self.now-timedelta(hours=1)).isoformat()
        self.assertEqual(extract([x],self.league,self.sport,self.now)["full_1x2_events"],0)
        x["commence_time"] = (self.now-timedelta(minutes=5)).isoformat()
        self.assertEqual(extract([x],self.league,self.sport,self.now)["upcoming_events"],0)

    def test_wrong_sport_does_not_count(self):
        x=copy.deepcopy(self.market); x["sport_key"]="soccer_japan_j_league"
        self.assertEqual(extract([x],self.league,self.sport,self.now)["upcoming_events"],0)

    def test_no_key_zero_calls(self):
        def bomb(*args):
            self.fail("network called without key")
        d=collect(token="",now=self.now,fetcher=bomb)
        self.assertEqual(d["status"],"NOT_CONFIGURED")
        self.assertEqual(d["requests_attempted"],0)
        self.assertTrue(validate(d,now=self.now))

    def test_one_catalogue_plus_six_bounded_calls(self):
        paths=[]
        def fake(path,key):
            self.assertEqual(key,"test-token")
            paths.append(path)
            return ([{"key": "soccer_epl", "active":True}, {"key": "soccer_efl_champ", "active":True}],998-len(paths))
        d=collect(token="test-token",now=self.now,fetcher=fake)
        self.assertEqual(d["requests_attempted"],7)
        self.assertEqual(len(paths),7)
        self.assertEqual([x["requests_attempted"] for x in d["coverage"]],[1]*6)
        self.assertTrue(all("bookmakers=" in x for x in paths[1:]))
        self.assertTrue(validate(d,now=self.now))
        self.assertFalse(d["raw_bookmaker_quotes_published"])

    def test_quota_reserve_stops_all_leagues(self):
        paths=[]
        def fake(path,key):
            paths.append(path)
            return ([],74)
        d=collect(token="test-token",now=self.now,fetcher=fake)
        self.assertEqual(d["requests_attempted"],1)
        self.assertEqual(len(paths),1)
        self.assertEqual(d["coverage"][0]["reason"],"QUOTA_RESERVE_75")

    def test_provider_error_fails_closed(self):
        def fake(path,key):
            if path=="/sports":
                return [],900
            raise ValueError("KEY_REJECTED_OR_SCOPE_DENIED")
        d=collect(token="test-token",now=self.now,fetcher=fake)
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["requests_attempted"],2)
        self.assertEqual(d["coverage"][0]["reason"],"KEY_REJECTED_OR_SCOPE_DENIED")
        self.assertFalse(d["automatic_model_change"])

    def test_no_model_promotion_even_complete_synthetic(self):
        def fake(path,key):
            if path=="/sports":
                return [],900
            if "soccer_epl/odds?markets=h2h,spreads,totals" in path:
                return [self.market],880
            return [],870
        d=collect(token="test-token",now=self.now,fetcher=fake)
        self.assertTrue(validate(d,now=self.now))
        self.assertEqual(d["coverage"][0]["paired_spread_events"],1)
        result=audit(d)
        self.assertEqual(result["total"],7)
        self.assertEqual(result["checks"][5]["state"],"HOLD")
        self.assertEqual(result["checks"][6]["state"],"PASS")
        self.assertFalse(result["can_promote_model"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_public_report_with_secret_or_raw_data_rejected(self):
        d=collect(token="",now=self.now)
        for key,val in (("production_recommendations","ENABLED"),
                        ("raw_bookmaker_quotes_published",True),
                        ("max_requests",120)):
            x=copy.deepcopy(d);x[key]=val
            with self.assertRaises(ValueError):
                validate(x,now=self.now)

if __name__=="__main__":
    unittest.main()
