"""Free-source adapter regression suite. No network or credentials needed."""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secondary_sources import (
    AF_ID, FD_CODE, LEAGUES, MAX_CALLS, SD_BD, SPORTMONKS_FREE_IDS,
    collect, fixture, parse_api_football, parse_api_football_odds_coverage,
    parse_football_data, parse_sportmonks, parse_sportsdb, utc
)

NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)


class Response:
    def __init__(self, value):
        self.data = json.dumps(value).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.data[:size]


class SecondarySourcesTests(unittest.TestCase):
    def test_six_league_mappings(self):
        self.assertEqual(set(LEAGUES), set(SD_BD))
        self.assertEqual(set(LEAGUES), set(AF_ID))
        self.assertEqual(set(LEAGUES), set(FD_CODE))
        self.assertLessEqual(MAX_CALLS["api_football"], 12)
        self.assertEqual(SPORTMONKS_FREE_IDS, (271, 501))

    def test_calendar_date_is_not_precise_utc(self):
        with self.assertRaisesRegex(ValueError, "INVALID_TIMESTAMP"):
            utc("2026-10-09")
        self.assertIsNone(fixture("epl", "A", "B", "2026-10-09", "f1"))

    def test_offset_aware_date_preserved(self):
        game = fixture("epl", "A", "B", "2026-10-09T19:30:00+08:00", "f1")
        self.assertEqual(game["kickoff_utc"], "2026-10-09T11:30:00+00:00")

    def test_no_unfinished_score_or_incomplete_score(self):
        g = fixture("epl", "A", "B", "2026-10-09T11:30:00Z", "1",
                    score=[2, 1], status="SCHEDULED")
        self.assertIsNone(g["score_ft"])
        g = fixture("epl", "A", "B", "2026-10-09T11:30:00Z", "1",
                    score=[2, None], status="FINISHED")
        self.assertIsNone(g["score_ft"])

    def test_sportsdb_league_mismatch_rejected(self):
        p = {"events":[{"idEvent":"101", "idLeague":str(SD_BD["epl"]),
                        "strHomeTeam":"Arsenal","strAwayTeam":"Chelsea",
                        "strTimestamp":"2026-10-10T14:00:00Z"}]}
        self.assertEqual(parse_sportsdb("bundesliga", p), [])
        self.assertEqual(len(parse_sportsdb("epl", p)), 1)

    def test_sportsdb_free_next_league_cap(self):
        p = {"events":[{
            "idEvent":str(i), "idLeague":str(SD_BD["epl"]),
            "strHomeTeam":"Arsenal", "strAwayTeam":"Chelsea",
            "strTimestamp":"2026-10-12T12:00:00Z"
        } for i in range(4)]}
        self.assertEqual(len(parse_sportsdb("epl", p, max_events=1)), 1)
        self.assertEqual(len(parse_sportsdb("epl", p, max_events=3)), 3)
        with self.assertRaisesRegex(ValueError, "UNAUTHORIZED_FREE"):
            parse_sportsdb("epl", p, max_events=100)

    def test_api_football_fulltime_and_league_filter(self):
        payload={"errors":[], "response":[{
            "fixture":{"id":77,"date":"2026-10-10T16:00:00+00:00",
                       "status":{"short":"FT"}},
            "league":{"id":AF_ID["bundesliga"]},
            "teams":{"home":{"name":"Bayern"},"away":{"name":"Leverkusen"}},
            "score":{"fulltime":{"home":2,"away":1}}
        }]}
        self.assertEqual(parse_api_football("bundesliga",payload)[0]["score_ft"],[2,1])
        self.assertEqual(parse_api_football("epl",payload),[])

    def test_api_football_vendor_errors_cannot_be_silent_data(self):
        with self.assertRaises(ValueError):
            parse_api_football("epl",{"errors":{"plan":"not entitled"},"response":[]})

    def test_1x2_probe_never_returns_bookmaker_prices(self):
        payload={"errors":[], "response":[{
            "fixture":{"id":312},
            "bookmakers":[{"name":"Nonpublic Vendor",
                           "bets":[{"id":1,"name":"Match Winner",
                                    "values":[{"value":"Home","odd":"2.75"}]}]}]}]}
        self.assertEqual(parse_api_football_odds_coverage("epl",payload),1)
        with self.assertRaises(ValueError):
            parse_api_football_odds_coverage("epl",{"errors":{"access":"blocked"},"response":[]})

    def test_football_data_fulltime_score(self):
        payload={"matches":[{
            "id":99,"competition":{"code":"BL1"},"utcDate":"2026-10-12T12:00:00Z",
            "status":"FINISHED","homeTeam":{"name":"Bayern"},
            "awayTeam":{"name":"Dortmund"},
            "score":{"fullTime":{"home":3,"away":2}}
        }]}
        self.assertEqual(parse_football_data("bundesliga",payload)[0]["score_ft"],[3,2])
        self.assertEqual(parse_football_data("seriea",payload),[])

    def test_sportmonks_free_tiers_only(self):
        self.assertEqual(parse_sportmonks({"data":{"id":271}}),271)
        self.assertIsNone(parse_sportmonks({"data":{"id":39}}))

    def test_no_key_only_six_league_sportsdb_requests(self):
        observed=[]
        def requester(req,timeout):
            observed.append(req.full_url)
            return Response({"events":[{"idEvent":"1",
                         "idLeague":str(SD_BD["epl"]),
                         "strHomeTeam":"A", "strAwayTeam":"B",
                         "strTimestamp":"2026-10-10T12:00:00Z"}]})
        output=collect(now=NOW,keys={},requester=requester)
        self.assertEqual(len(observed),36)
        self.assertEqual([x["status"] for x in output["providers"][1:]],
                         ["NOT_CONFIGURED"]*3)
        self.assertEqual(output["production_recommendations"],"DISABLED")
        self.assertFalse(output["odds_fallback_confirmed"])
        self.assertFalse(output["six_league_independent_results_verified"])

    def test_optional_keys_never_appear_in_urls_or_derived_results(self):
        sentinel="UNIQUE_PLEASE_NEVER_LOG_THIS_SECRET_128"
        observed=[]
        def requester(req,timeout):
            observed.append((req.full_url,dict(req.header_items())))
            url=req.full_url
            if "api.sportmonks" in url:
                return Response({"data":{"id":int(url.rsplit("/",1)[-1])}})
            if "football-data.org" in url:
                return Response({"matches":[]})
            if "football.api-sports.io" in url:
                return Response({"errors":[],"response":[]})
            return Response({"events":[]})
        result=collect(now=NOW,keys={
            "API_FOOTBALL_KEY":sentinel,
            "FOOTBALL_DATA_ORG_TOKEN":sentinel,
            "SPORTMONKS_API_TOKEN":sentinel
        },requester=requester)
        self.assertTrue(observed)
        self.assertNotIn(sentinel,json.dumps(result))
        self.assertTrue(all(sentinel not in url and "api_token=" not in url
                            for url,_ in observed))
        self.assertLessEqual(result["providers"][1]["calls_attempted"],12)

    def test_401_and_403_stop_optional_provider_queries(self):
        for code in (401,403):
            called=[]
            def requester(req,timeout):
                called.append(req.full_url)
                if "football.api-sports.io" in req.full_url:
                    raise HTTPError(req.full_url,code,"Access",None,None)
                return Response({"events":[]})
            result=collect(now=NOW,keys={"API_FOOTBALL_KEY":"unusable"},
                           requester=requester)
            self.assertLessEqual(result["providers"][1]["calls_attempted"],1)
            self.assertEqual(result["providers"][1]["status"],"HOLD")

    def test_2026_free_season_rejected_skips_all_odds_probes(self):
        observed=[]
        def requester(req,timeout):
            observed.append(req.full_url)
            if "football.api-sports.io" in req.full_url:
                return Response({"errors":{"plan":"This season not available on Free plan"},
                                 "response":[]})
            return Response({"events":[]})
        result=collect(now=NOW,keys={"API_FOOTBALL_KEY":"configured"},
                       requester=requester)
        self.assertEqual(result["providers"][1]["calls_attempted"],1)
        self.assertFalse(result["providers"][1]["current_season_entitled"])
        self.assertFalse(any("/odds?" in url for url in observed))

    def test_sensitive_bookmaker_payload_dropped(self):
        def requester(req,timeout):
            return Response({"events":[{
                "idEvent":"1", "idLeague":str(SD_BD["epl"]),
                "strHomeTeam":"Arsenal","strAwayTeam":"Chelsea",
                "strTimestamp":"2026-10-10T19:00:00Z",
                "bookmaker":{"odds":9999},
            }]})
        result=collect(now=NOW,keys={},requester=requester)
        self.assertNotIn("9999",json.dumps(result))
        self.assertFalse(result["original_api_payload_redistributed"])


if __name__=="__main__":
    unittest.main()
