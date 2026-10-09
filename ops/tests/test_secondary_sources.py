"""Four independent free-tier source adapters; no paid calls or secrets leaked."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secondary_sources import (LEAGUES, SD_BD, AF_ID, FD_CODE, MAX_CALLS,
    collect, fixture, parse_sportsdb, parse_api_football, parse_api_football_odds_coverage,
    parse_football_data,
    parse_sportmonks, fetch, NoRedirect)

NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)


class Payload:
    def __init__(self, object_):
        self.body = json.dumps(object_).encode()
    def read(self, n):
        return self.body[:n]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class AdapterTests(unittest.TestCase):
    def test_all_six_leagues_mapped_to_both_public_apis(self):
        self.assertEqual(set(SD_BD), set(LEAGUES))
        self.assertEqual(set(AF_ID), set(LEAGUES))
        self.assertEqual(set(FD_CODE), set(LEAGUES))
        self.assertEqual(MAX_CALLS["api_football"], 12)

    def test_free_thesportsdb_only_one_next_event_each(self):
        d = {"events":[{
            "idEvent":str(300+n),"idLeague":str(SD_BD["epl"]),
            "strHomeTeam":"Arsenal","strAwayTeam":"Chelsea",
            "strTimestamp":"2026-10-12T19:00:00","strStatus":"NS"} for n in range(4)]}
        self.assertEqual(len(parse_sportsdb("epl", d)), 1)
        self.assertEqual(parse_sportsdb("bundesliga", d), [])

    def test_free_thesportsdb_no_fake_utc_offset_or_scores(self):
        p = parse_sportsdb("epl", {"events":[
            {"idEvent":"99","idLeague":str(SD_BD["epl"]),
             "strHomeTeam":"Arsenal","strAwayTeam":"Chelsea",
             "strTimestamp":"2026-10-10T11:30:00","strStatus":"NS",
             "intHomeScore":None,"intAwayScore":None}]})[0]
        self.assertTrue(p["kickoff_utc"].endswith("+00:00"))
        self.assertIsNone(p["score_ft"])
        self.assertEqual(p["status"],"SCHEDULED")

    def test_no_date_no_kickoff_invented(self):
        self.assertIsNone(fixture("epl","A","B",None,"id"))
        self.assertIsNone(fixture("epl","A","B","2026-01-01","id",score=[2,1]))

    def test_api_football_parses_fulltime_and_league(self):
        d={"errors":[],"response":[{
            "fixture":{"id":88,"date":"2026-10-12T17:00:00+00:00",
                       "status":{"short":"FT"}},
            "league":{"id":AF_ID["laliga"]},
            "teams":{"home":{"name":"Barcelona"},"away":{"name":"Real Madrid"}},
            "score":{"fulltime":{"home":1,"away":2}}}]}
        p = parse_api_football("laliga",d)[0]
        self.assertEqual(p["score_ft"],[1,2])
        self.assertEqual(p["provider_event_id"],"88")
        self.assertEqual(parse_api_football("epl",d),[])

    def test_optional_api_football_odds_probe_counts_only_and_never_discloses_prices(self):
        payload={"errors":[], "response":[{
            "fixture":{"id":3141},
            "bookmakers":[{"name":"Sensitive Licensed Sportsbook",
                           "bets":[{"id":1,"name":"Match Winner",
                                    "values":[{"value":"Home","odd":"1.2"},
                                              {"value":"Draw","odd":"8.0"},
                                              {"value":"Away","odd":"20.0"}]}]}]}]}
        self.assertEqual(parse_api_football_odds_coverage("epl",payload),1)
        self.assertEqual(parse_api_football_odds_coverage("laliga",{"errors":[], "response":[]}),0)
        with self.assertRaisesRegex(ValueError,"ODDS_NOT_AVAILABLE"):
            parse_api_football_odds_coverage("epl",{"errors":{"plan":"not allowed"},"response":[]})

    def test_football_data_delayed_90_minute_score(self):
        d={"matches":[{
            "id":44,"competition":{"code":"BL1"},"utcDate":"2026-10-12T12:00:00Z",
            "homeTeam":{"name":"Bayern"},"awayTeam":{"name":"Cologne"},
            "status":"FINISHED","score":{"fullTime":{"home":3,"away":0}}}]}
        rows=parse_football_data("bundesliga",d)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["score_ft"],[3,0])
        self.assertEqual(parse_football_data("seriea",d),[])

    def test_sportmonks_free_leagues_only(self):
        self.assertEqual(parse_sportmonks({"data":{"id":271,"name":"Danish"}}),271)
        self.assertIsNone(parse_sportmonks({"data":{"id":78,"name":"Bundesliga"}}))

    def test_unconfigured_optional_providers_never_called(self):
        seen=[]
        def fake(req,timeout):
            seen.append(req.full_url)
            league=int(req.full_url.split("id=")[-1])
            return Payload({"events":[{
                "idEvent":str(league),"idLeague":str(league),
                "strHomeTeam":"Home","strAwayTeam":"Away",
                "strTimestamp":"2026-10-10T12:00:00","strStatus":"NS"}]})
        r=collect(now=NOW,keys={},requester=fake)
        self.assertEqual(len(seen),6)
        self.assertEqual(len(r["sampled_fixtures"]),6)
        self.assertTrue(all(not any("api_token=" in url for url in seen) for _ in [0]))
        self.assertEqual(r["providers"][0]["status"],"PARTIAL_COVERAGE")
        self.assertEqual([x["status"] for x in r["providers"][1:]],["NOT_CONFIGURED"]*3)
        self.assertFalse(r["coverage_is_complete"])
        self.assertFalse(r["six_league_independent_results_verified"])

    def test_optional_credentials_never_enter_urls_or_outputs(self):
        secret="THIS_IS_A_SENTINEL_SECRET_12345"
        observed=[]
        def fake(req,timeout):
            observed.append((req.full_url, dict(req.header_items())))
            if "api.sportmonks" in req.full_url:
                league=int(req.full_url.rsplit("/",1)[-1])
                return Payload({"data":{"id":league,"name":"Free league"}})
            if "api.football-data.org" in req.full_url:
                return Payload({"matches":[]})
            if "football.api-sports.io" in req.full_url:
                return Payload({"errors":[],"response":[]})
            return Payload({"events":[]})
        r=collect(now=NOW,keys={"API_FOOTBALL_KEY":secret,
                                 "FOOTBALL_DATA_ORG_TOKEN":secret,
                                 "SPORTMONKS_API_TOKEN":secret},requester=fake)
        self.assertEqual(len(observed),26)
        self.assertNotIn(secret,json.dumps(r))
        self.assertTrue(all(secret not in url and "api_token=" not in url for url,_ in observed))
        self.assertEqual(r["providers"][-1]["additional_non_target_free_leagues"],2)

    def test_http_401_short_circuits_without_exposing_request_url(self):
        def unauthorized(req,timeout):
            raise HTTPError(req.full_url,401,"KEY",None,None)
        body,err=fetch("api_football","https://v3.football.api-sports.io/leagues",
                       {"x-apisports-key":"TESTSECRET"},requester=unauthorized)
        self.assertIsNone(body)
        self.assertEqual(err,"KEY_OR_PLAN_REJECTED")

    def test_unauthorized_key_stops_after_first_attempt(self):
        calls=[]
        def fake(req,timeout):
            calls.append(req.full_url)
            if "football.api-sports.io" in req.full_url:
                raise HTTPError(req.full_url,403,"NO",None,None)
            return Payload({"events":[]})
        s=collect(now=NOW,keys={"API_FOOTBALL_KEY":"NOACCESS"},requester=fake)
        self.assertEqual(s["providers"][1]["calls_attempted"],1)
        self.assertEqual(s["providers"][1]["status"],"HOLD")

    def test_no_raw_prices_even_if_provider_contains_odds(self):
        def fake(req,timeout):
            return Payload({"events":[{
                "idEvent":"100","idLeague":str(SD_BD["epl"]),
                "strHomeTeam":"Arsenal","strAwayTeam":"Chelsea",
                "strTimestamp":"2026-10-10T11:30:00",
                "bookmaker":{"price":99.99},"strStatus":"NS"}]})
        report=collect(now=NOW,keys={},requester=fake)
        self.assertNotIn("99.99",json.dumps(report))
        self.assertFalse(report["odds_fallback_confirmed"])
        self.assertEqual(report["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
