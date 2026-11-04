"""No-network checks for permitted low-credit J1 market source adapters."""
import copy
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import japan_free_market as jfm
from japan_free_market import (
    SPORT, collect, crosscheck, odds_japan, prop_line,
    rundown, _rundown_date, utc
)


class Headers(dict):
    pass


class Response:
    def __init__(self, body, quota):
        self.body=json.dumps(body).encode("utf-8")
        self.headers=Headers(quota)
    def read(self,n):
        return self.body[:n]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


class JapanFreeMarketTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,0,0,tzinfo=timezone.utc)
        self.ko=self.now+timedelta(days=1)
        m=self.now-timedelta(minutes=3)
        self.j1={
            "id":"j1-999", "sport_key":SPORT,
            "home_team":"FC Tokyo","away_team":"Urawa Reds",
            "commence_time":self.ko.isoformat(),
            "bookmakers":[]
        }
        for key, prices in (
            ("book_1",{"home":2.25,"draw":3.30,"away":3.25}),
            ("book_2",{"home":2.28,"draw":3.35,"away":3.20})
        ):
            self.j1["bookmakers"].append({
                "key":key,
                "markets":[
                    {"key":"h2h","last_update":m.isoformat(),
                     "outcomes":[{"name":"FC Tokyo","side":"home","price_decimal":prices["home"]},
                                 {"name":"Draw","side":"draw","price_decimal":prices["draw"]},
                                 {"name":"Urawa Reds","side":"away","price_decimal":prices["away"]}]},
                    {"key":"spreads","last_update":m.isoformat(),
                     "outcomes":[{"name":"FC Tokyo","side":"home","price":-110,"point":-0.25},
                                 {"name":"Urawa Reds","side":"away","price":-110,"point":+0.25}]},
                    {"key":"totals","last_update":m.isoformat(),
                     "outcomes":[{"name":"Over","price_decimal":1.93,"point":2.5},
                                 {"name":"Under","price_decimal":1.94,"point":2.5}]}
                ]})
        self.date={str(19):{"dates":[self.ko.timestamp()]}}
        self.market={
            "events":[{"event_id":"rid","sport_id":19,"event_date":self.ko.isoformat(),
                       "markets":[{"market_id":id,"participants":[
                           {"id":pid,"lines":[{"prices":{
                               "19":{"price":-110,"updated_at":m.isoformat()},
                               "22":{"price":120,"updated_at":m.isoformat()}}}]}
                           for pid in (100,101,102)]}
                           for id in (1,2,3)]}]
        }
        self.odds_event={
            "id":"odds_999","home_team":"FC Tokyo","away_team":"Urawa Reds",
            "commence_time":self.ko.isoformat(),"bookmakers":[{
                "key":key, "markets":[{
                    "key":"h2h","last_update":m.isoformat(),
                    "outcomes":[{"name":"FC Tokyo","price":2.25},
                                {"name":"Draw","price":3.3},
                                {"name":"Urawa Reds","price":3.25}]
                }]
            } for key in ("book_1","book_2")]
        }

    def _collect_filtered_propline_response(self, raw):
        expected = (
            "https://api.prop-line.com/v1/sports/soccer_japan_j_league/odds"
            "?markets=h2h,spreads,totals"
            "&bookmakers=pinnacle,bovada,fanduel,draftkings"
        )
        reads = []

        class BoundedResponse:
            headers = {"X-Daily-Remaining": "998"}

            def read(response, size):
                reads.append(size)
                return raw[:size]

            def __enter__(response):
                return response

            def __exit__(response, *args):
                return False

        def fake_opener(request, timeout):
            self.assertEqual(request.full_url, expected)
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.get_header("X-api-key"), "synthetic-test-only")
            self.assertNotIn("synthetic-test-only", request.full_url)
            self.assertEqual(timeout, 15)
            return BoundedResponse()

        with patch.object(jfm, "urlopen", side_effect=fake_opener) as opener:
            report = jfm.collect(
                {"PROPLINE_API_KEY": "synthetic-test-only"},
                now=self.now, requester=jfm.fetch)
        opener.assert_called_once()
        self.assertEqual(jfm.MAX_BLOB, 1_700_000)
        self.assertEqual(reads, [1_700_001])
        state = report["j1_free_prematch_sources"][0]
        self.assertEqual(state["requests_attempted"], 1)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["bet_recommendation_count"], 0)
        self.assertFalse(report["raw_bookmaker_prices_or_names_redistributed"])
        for forbidden in ("synthetic-test-only", "pinnacle", "bovada",
                          "fanduel", "draftkings", "price_decimal"):
            self.assertNotIn(forbidden, json.dumps(report))
        return state

    def test_propline_fixed_filtered_bulk_request_accepts_fresh_consensus(self):
        event = copy.deepcopy(self.j1)
        for book, key in zip(event["bookmakers"], ("pinnacle", "bovada")):
            book["key"] = key
        state = self._collect_filtered_propline_response(
            json.dumps([event]).encode("utf-8"))
        self.assertEqual(state["status"], "RESEARCH_ONLY")
        self.assertEqual(state["fresh_3way_event_count"], 1)
        self.assertEqual(state["provider_daily_remaining"], 998)

    def test_propline_filtered_oversize_holds_without_retry_or_fallback(self):
        state = self._collect_filtered_propline_response(b"x" * 1_700_001)
        self.assertEqual(state["status"], "HOLD")
        self.assertEqual(state["reason"], "UPSTREAM_OVERSIZE")
        self.assertEqual(state["fresh_3way_event_count"], 0)
        self.assertEqual(state["fresh_spread_event_count"], 0)
        self.assertEqual(state["fresh_totals_event_count"], 0)

    def test_propline_fresh_1x2_spreads_totals(self):
        s, c=prop_line([self.j1],now=self.now)
        self.assertEqual(s["upcoming_events"],1)
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(s["fresh_spread_event_count"],1)
        self.assertEqual(s["fresh_totals_event_count"],1)
        self.assertEqual(s["status"],"RESEARCH_ONLY")
        self.assertEqual(len(c),1)
        self.assertAlmostEqual(sum(list(c.values())[0]),1,places=6)

    def test_single_book_rejected_from_consensus(self):
        self.j1["bookmakers"]=self.j1["bookmakers"][:1]
        s,c=prop_line([self.j1],now=self.now)
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(len(c),0)

    def test_stale_and_inplay_quotes_do_not_become_pre_match(self):
        for book in self.j1["bookmakers"]:
            for m in book["markets"]:
                m["last_update"]=(self.now-timedelta(hours=2)).isoformat()
        s,c=prop_line([self.j1],now=self.now)
        self.assertEqual(s["fresh_3way_event_count"],0)
        self.assertEqual(s["fresh_spread_event_count"],0)
        self.assertGreater(s["free_stale_quote_rejects"],0)
        self.j1["commence_time"]=(self.now-timedelta(minutes=1)).isoformat()
        s,c=prop_line([self.j1],now=self.now)
        self.assertEqual(s["upcoming_events"],0)

    def test_propline_american_prices_will_not_be_mistaken_for_decimal(self):
        for book in self.j1["bookmakers"]:
            for o in book["markets"][0]["outcomes"]:
                del o["price_decimal"]
            book["markets"][0]["outcomes"][0]["price"]=+125
            book["markets"][0]["outcomes"][1]["price"]=+230
            book["markets"][0]["outcomes"][2]["price"]=+220
        s,c=prop_line([self.j1],now=self.now)
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertTrue(all(.1<p<.6 for p in list(c.values())[0]))

    def test_rundown_delayed_free_main_lines_and_date(self):
        self.assertEqual(_rundown_date(self.date,self.now),self.ko.date().isoformat())
        s=rundown(self.date,self.market,now=self.now)
        self.assertEqual(s["status"],"RESEARCH_ONLY")
        self.assertEqual(s["fresh_3way_event_count"],1)
        self.assertEqual(s["fresh_spread_event_count"],1)
        self.assertEqual(s["fresh_totals_event_count"],1)
        self.assertFalse(s["market_quotes_are_not_executable"] is False)

    def test_rundown_does_not_count_one_outcome_three_times_as_threeway(self):
        self.market["events"][0]["markets"][0]["participants"] = (
            self.market["events"][0]["markets"][0]["participants"][:1])
        status=rundown(self.date,self.market,now=self.now)
        self.assertEqual(status["fresh_3way_event_count"],0)
        self.assertEqual(status["fresh_spread_event_count"],1)
        self.assertEqual(status["fresh_totals_event_count"],1)

    def test_no_sport_in_rundown_dates_no_paid_lookup(self):
        self.assertIsNone(_rundown_date({},self.now))
        self.assertIsNone(_rundown_date({"19":{"dates":[self.now.timestamp()-9000]}},self.now))

    def test_odds_api_spare_quota_floor(self):
        calls=[]
        def opener(req,timeout):
            url=req.full_url.split("?")[0]
            calls.append(url)
            if url.endswith("/sports/"):
                return Response([{"key":SPORT,"active":True}],
                                {"x-requests-used":"260","x-requests-remaining":"240"})
            return Response([self.odds_event],
                            {"x-requests-used":"261","x-requests-remaining":"239"})
        s,c=odds_japan("private-test-key",now=self.now,opener=opener)
        self.assertEqual(s["status"],"HOLD")
        self.assertEqual(s["reason"],"PRESERVE_EXISTING_SIX_LEAGUE_FREE_CREDITS")
        self.assertEqual(len(calls),1)
        self.assertNotIn("private-test-key",json.dumps(s))

    def test_odds_api_j1_research_quote_and_crosscheck_not_independence(self):
        def opener(req,timeout):
            url=req.full_url.split("?")[0]
            if url.endswith("/sports/"):
                return Response([{"key":SPORT,"active":True}],
                                {"x-requests-used":"50","x-requests-remaining":"450"})
            return Response([self.odds_event],
                            {"x-requests-used":"51","x-requests-remaining":"449"})
        s,c=odds_japan("test",now=self.now,opener=opener)
        self.assertEqual(s["fresh_3way_event_count"],1)
        pl,pc=prop_line([self.j1],now=self.now)
        cross=crosscheck(pc,c)
        self.assertEqual(cross["same_fixture_two_api_observations"],1)
        self.assertTrue(cross["api_provider_count_is_not_independent_bookmaker_count"])
        self.assertFalse(cross["independent_venue_quote_verified"])

    def test_full_collect_skips_all_missing_key_without_network(self):
        def no_network(*args,**kwargs):
            raise AssertionError("should not call provider without key")
        d=collect({},now=self.now,requester=no_network,odds_opener=no_network)
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["bet_recommendation_count"],0)
        self.assertEqual(d["production_recommendations"],"DISABLED")
        self.assertEqual([s["status"] for s in d["j1_free_prematch_sources"]],
                         ["NOT_CONFIGURED"]*3)
        self.assertFalse(d["raw_bookmaker_prices_or_names_redistributed"])
        self.assertNotIn('"decimal_odds"',json.dumps(d))
        self.assertFalse(d["realtime_inplay_quotes_confirmed"])

    def test_mock_all_sources_does_not_publish_any_bookmaker_prices(self):
        requested=[]
        def mocked(url,headers):
            requested.append(url)
            if "prop-line" in url:
                self.assertIn("X-API-Key",headers)
                self.assertNotIn("test-prop",url)
                return [self.j1],{"X-Daily-Remaining":"998"}
            if "/sports/dates?" in url:
                self.assertIn("sport_ids=19",url)
                self.assertIn("format=epoch",url)
                self.assertIn("X-TheRundown-Key",headers)
                return self.date,{}
            self.assertIn("/sports/19/events/",url)
            return self.market,{}
        def odds_opener(req,timeout):
            if req.full_url.split("?")[0].endswith("/sports/"):
                return Response([{"key":SPORT,"active":True}],
                                {"x-requests-used":"50","x-requests-remaining":"450"})
            return Response([self.odds_event],
                            {"x-requests-used":"51","x-requests-remaining":"449"})
        d=collect({"PROPLINE_API_KEY":"test-prop","THERUNDOWN_API_KEY":"test-run",
                   "THE_ODDS_API_KEY":"test-odds"},now=self.now,
                  requester=mocked,odds_opener=odds_opener)
        self.assertEqual(len(requested),3)
        self.assertEqual([s["status"] for s in d["j1_free_prematch_sources"]],
                         ["RESEARCH_ONLY"]*3)
        self.assertEqual(d["cross_feed_consistency_observation"][
            "same_fixture_two_api_observations"],1)
        self.assertFalse(d["free_tier_closing_lines_available"])
        self.assertFalse(d["raw_bookmaker_prices_or_names_redistributed"])
        self.assertNotIn("test-prop",json.dumps(d))
        self.assertNotIn("test-run",json.dumps(d))
        self.assertNotIn("test-odds",json.dumps(d))
        self.assertNotIn("book_1",json.dumps(d))
        self.assertNotIn('"price_decimal"',json.dumps(d))
        self.assertEqual(d["bet_recommendation_count"],0)


if __name__=="__main__":
    unittest.main()
