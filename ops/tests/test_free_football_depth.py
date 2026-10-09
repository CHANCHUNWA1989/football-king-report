"""Synthetic, zero-network extra football research API coverage tests."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from free_football_depth import (
    collect, get_json, tsdb_rows, openliga_rows, figshare_rows,
    TSDB, OLDB, FIG, TOTAL_BUDGET, TSDB_LEAGUES, GERMAN_LEAGUES,
)

CLOCK=datetime(2026,10,9,13,tzinfo=timezone.utc)


class MockResponse:
    def __init__(self,payload):
        self.content=json.dumps(payload).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,count): return self.content[:count]


class FootballDepthTests(unittest.TestCase):
    def setUp(self):
        self.urls=[]
        self.paces=[]
        def opener(request,timeout):
            url=request.full_url
            self.urls.append(url)
            self.assertNotIn("apiKey",url)
            if url.startswith(TSDB):
                import urllib.parse
                q=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                self.assertEqual(q.get("s"),["2026-2027"])
                league_id=q["l"][0]
                return MockResponse({"table":[{
                    "idLeague":league_id,"idTeam":str(i+1),
                    "strTeam":"FC "+league_id+" "+str(i),"intRank":str(i+1),
                    "intPoints":str(30-i)} for i in range(5)]})
            if url.startswith(OLDB):
                return MockResponse([{
                    "teamInfo":{"teamName":f"Example Club {i}","teamId":i+100},
                    "points":i*2,"matches":9
                } for i in range(18)])
            if url.startswith(FIG):
                return MockResponse([
                    {"id":7770599,"title":"Events"},
                    {"id":7770598,"title":"Matches"},
                    {"id":7770597,"title":"Teams"}])
            self.fail("UNAPPROVED_URL")
        self.opener=opener

    def test_one_weekly_batch_is_bounded_and_all_data_research_only(self):
        doc=collect(now=CLOCK,requester=self.opener)
        self.assertEqual(doc["requests_attempted"],TOTAL_BUDGET)
        self.assertEqual(len(self.urls),10)
        self.assertEqual(doc["valid_sources"],10)
        self.assertEqual(sum(x["valid_rows"] for x in doc["observations"]),6*5+3*18+3)
        self.assertEqual(doc["status"],"RESEARCH_ONLY")
        self.assertFalse(doc["source_data_independently_verified"])
        self.assertFalse(doc["full_six_league_standings_verified"])
        self.assertTrue(doc["current_team_probabilities_unchanged"])
        self.assertFalse(doc["bookmaker_quotes_available"])
        self.assertEqual(doc["production_recommendations"],"DISABLED")
        self.assertEqual(doc["six_core_leagues_research_targeted"],6)
        self.assertNotIn("FC ",json.dumps(doc))

    def test_no_advance_future_models_or_betting(self):
        doc=collect(now=CLOCK,requester=self.opener)
        self.assertFalse(doc["historical_archive_is_live"])
        self.assertTrue(doc["historical_2017_18_events_not_2026_current"])
        self.assertTrue(doc["source_uses_current_season_not_sealed_past_forecast"])
        self.assertFalse(doc["original_provider_payload_redistributed"])
        self.assertTrue(all(x["raw_data_published"] is False for x in doc["observations"]))

    def test_sportsdb_free_five_rows_limit_does_not_claim_full_table(self):
        self.assertEqual(tsdb_rows({"table":[{"strTeam":f"Team{i}"} for i in range(5)]},4328),5)
        with self.assertRaises(ValueError):
            tsdb_rows({"table":[{"strTeam":f"Team{i}"} for i in range(6)]},4328)
        self.assertEqual(tsdb_rows({"table":None},4328),0)

    def test_openliga_table_does_not_duplicate_teams(self):
        self.assertEqual(openliga_rows([{"teamInfo":{"teamName":"A"},"points":5}]),(1,1))
        with self.assertRaises(ValueError):
            openliga_rows([{"teamInfo":{"teamName":"A"},"points":5},
                           {"teamInfo":{"teamName":"A"},"points":6}])
        self.assertEqual(openliga_rows([{"teamInfo":{"teamName":"A"},"points":True}]),(1,0))

    def test_figshare_metadata_only_and_bounded(self):
        self.assertEqual(figshare_rows([{"id":123,"title":"Events"}]),1)
        with self.assertRaises(ValueError):
            figshare_rows([{"id":i,"title":"Events"} for i in range(11)])

    def test_http_429_stops_same_provider_but_checks_other_providers(self):
        seen=[]
        def fake(req,timeout):
            seen.append(req.full_url)
            if req.full_url.startswith(TSDB):
                raise HTTPError(req.full_url,429,"free quota",{},None)
            return self.opener(req,timeout)
        doc=collect(now=CLOCK,requester=fake)
        self.assertEqual(doc["requests_attempted"],1+len(GERMAN_LEAGUES)+1)
        self.assertTrue(all(x["status"]=="HOLD" for x in doc["observations"][:6]))
        self.assertEqual(doc["observations"][1]["reason"],"PROVIDER_RATE_LIMIT_STOP")
        self.assertEqual(doc["valid_sources"],4)

    def test_unknown_source_url_disallowed(self):
        with self.assertRaisesRegex(ValueError,"OUT_OF_SCOPE_PUBLIC_API"):
            get_json("https://fake.com/user/tokens",opener=self.opener)

    def test_sources_bad_payloads_fail_closed(self):
        def fake(req,timeout):
            return MockResponse({"unexpected":123})
        doc=collect(now=CLOCK,requester=fake)
        self.assertEqual(doc["status"],"HOLD")
        self.assertEqual(doc["valid_sources"],0)
        self.assertTrue(all(x["status"]=="HOLD" for x in doc["observations"]))


    def test_empty_german_official_table_uses_bounded_community_score_fallback(self):
        fallback_urls=[]
        def getter(request,timeout):
            u=request.full_url
            if u.startswith(OLDB) and "getbltable/" in u:
                return MockResponse([])
            if "/getmatchdata/" in u:
                fallback_urls.append(u)
                shortcut=u.split("/")[-2]
                return MockResponse([{
                    "matchID":100+i,"leagueShortcut":shortcut,
                    "matchDateTimeUTC":"2026-09-12T14:30:00Z",
                    "matchIsFinished":True,
                    "team1":{"teamId":100,"teamName":"FC Sample A"},
                    "team2":{"teamId":200,"teamName":"FC Sample B"},
                    "matchResults":[{"resultTypeID":1,"pointsTeam1":0,"pointsTeam2":0},
                                    {"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]
                } for i in range(1)])
            return self.opener(request,timeout)
        results=collect(now=CLOCK,requester=getter)
        self.assertEqual(results["requests_attempted"],TOTAL_BUDGET+3)
        self.assertEqual(len(fallback_urls),3)
        rows=[row for row in results["observations"] if row["provider"]=="openligadb_table"]
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertEqual(row["status"],"PARTIAL")
            self.assertEqual(row["derived_clubs_with_points"],2)
            self.assertEqual(row["season_finished_games_sampled"],1)
            self.assertEqual(row["reason"],"COMMUNITY_SCORE_DERIVED_COUNTS_NOT_OFFICIAL_STANDINGS")
            self.assertFalse(row["official_league_table_confirmed"])
        self.assertFalse(results["full_six_league_standings_verified"])
        self.assertEqual(results["production_recommendations"],"DISABLED")

    def test_empty_table_and_empty_season_stays_hold(self):
        def empty(request,timeout):
            if request.full_url.startswith(OLDB) or "/getmatchdata/" in request.full_url:
                return MockResponse([])
            return self.opener(request,timeout)
        report=collect(now=CLOCK,requester=empty)
        self.assertEqual(report["requests_attempted"],TOTAL_BUDGET+3)
        assert all(row["status"]=="HOLD" for row in report["observations"]
                   if row["provider"]=="openligadb_table")



if __name__=="__main__":
    unittest.main()
