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

    def test_overflow_preserves_all_leagues_and_reconciles_public_counts(self):
        from source_publish_guard import verify, MAX_PUBLIC_FIXTURES
        from urllib.parse import urlsplit
        now = datetime.now(timezone.utc)
        def requester(req, timeout):
            url = req.full_url
            if "football-data.org" in url:
                code = urlsplit(url).path.split("/")[-2]
                return Response({"matches": [
                    {"id": i, "competition": {"code": code},
                     "utcDate": (now + timedelta(hours=i-1)).isoformat(),
                     "status": "FINISHED" if i == 0 else "TIMED",
                     "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"},
                     "score": {"fullTime": {"home": 2, "away": 1}}}
                    for i in range(35)
                ]})
            return Response({"events": []})
        report = collect(now=now, keys={"FOOTBALL_DATA_ORG_TOKEN": "fake"},
                         requester=requester)
        state = report["providers"][2]
        self.assertEqual(len(report["sampled_fixtures"]), MAX_PUBLIC_FIXTURES)
        self.assertEqual(state["sampled_fixture_count"], MAX_PUBLIC_FIXTURES)
        self.assertEqual(sum(state["counts_by_league"].values()), MAX_PUBLIC_FIXTURES)
        self.assertTrue(all(n == 25 for n in state["counts_by_league"].values()))
        self.assertEqual(sum(row["status"] == "FINISHED"
                             for row in report["sampled_fixtures"]), 6)
        self.assertIn("PUBLIC_SAMPLE_CAP_TRUNCATED", state["warnings"])
        self.assertEqual(state["status"], "PARTIAL")
        verify(report, now=datetime.now(timezone.utc))

    def test_live_overflow_shape_preserves_six_leagues_and_existing_source(self):
        # Reproduce the observed run 46115528419 provider/league counts,
        # using synthetic rows only: no commercial payloads or credentials.
        from collections import Counter
        from source_publish_guard import verify, MAX_PUBLIC_FIXTURES
        from secondary_sources import bound_public_sample
        now = datetime.now(timezone.utc)
        report = collect(now=now, keys={}, requester=lambda req, timeout:
                         Response({"events": []}))
        distributions = {
            "thesportsdb": (8, 6, 7, 8, 9, 7),
            "football_data_org": (30, 24, 18, 21, 18, 18),
        }
        for provider, counts in distributions.items():
            state = next(p for p in report["providers"] if p["provider"] == provider)
            state.update(configured=True, status="PARTIAL_COVERAGE",
                         counts_by_league=dict(zip(LEAGUES, counts)),
                         sampled_fixture_count=sum(counts))
            for league, count in zip(LEAGUES, counts):
                for i in range(count):
                    row = fixture(league, "A", "B",
                                  (now + timedelta(hours=i-2)).isoformat(),
                                  str(i), score=[2, 1] if i == 0 else None,
                                  status="FINISHED" if i == 0 else "SCHEDULED")
                    row["provider"] = provider
                    report["sampled_fixtures"].append(row)
            if provider == "thesportsdb":
                state["recent_final_score_observations"] = 6
        self.assertEqual(len(report["sampled_fixtures"]), 174)
        bound_public_sample(report, now)
        self.assertEqual(len(report["sampled_fixtures"]), MAX_PUBLIC_FIXTURES)
        counts = Counter((row["provider"], row["league"])
                         for row in report["sampled_fixtures"])
        self.assertEqual(sum(counts["thesportsdb", l] for l in LEAGUES), 45)
        self.assertEqual(sum(counts["football_data_org", l] for l in LEAGUES), 105)
        self.assertTrue(all(counts["football_data_org", l] >= 17 for l in LEAGUES))
        self.assertEqual(sum(row["status"] == "FINISHED"
                             for row in report["sampled_fixtures"]), 12)
        self.assertFalse(report["six_league_independent_results_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        verify(report, now=now)
        # Reapplying the cap to a bounded report must be idempotent.
        before = json.dumps(report, sort_keys=True)
        bound_public_sample(report, now)
        self.assertEqual(json.dumps(report, sort_keys=True), before)

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
        self.assertEqual(len(observed),48)
        self.assertEqual([x["status"] for x in output["providers"][1:]],
                         ["NOT_CONFIGURED"]*3)
        self.assertEqual(output["production_recommendations"],"DISABLED")
        self.assertFalse(output["odds_fallback_confirmed"])
        self.assertFalse(output["six_league_independent_results_verified"])

    def test_six_leagues_get_equal_priority_even_if_quota_stops_early(self):
        seen=[]
        def requester(req,timeout):
            seen.append(req.full_url)
            return Response({"events":[]})
        collect(now=NOW,keys={},requester=requester)
        # Every league gets today and the two recent dates before previews.
        for pos,code in enumerate(LEAGUES):
            for round_index, day in enumerate(("2026-10-09", "2026-10-08", "2026-10-07")):
                self.assertIn("eventsday.php",seen[pos+6*round_index])
                self.assertIn("d="+day,seen[pos+6*round_index])
                self.assertIn("l="+str(SD_BD[code]),seen[pos+6*round_index])
            self.assertIn("eventspastleague.php",seen[pos+18])
            self.assertIn("id="+str(SD_BD[code]),seen[pos+18])
            self.assertIn("eventsnextleague.php",seen[pos+24])
            self.assertIn("id="+str(SD_BD[code]),seen[pos+24])
        self.assertEqual(len(seen),48)

    def test_recent_fulltime_days_use_no_additional_free_calls(self):
        from urllib.parse import parse_qs, urlsplit

        seen = []
        def requester(req, timeout):
            url = req.full_url
            seen.append(url)
            if "eventsday.php" not in url:
                return Response({"events": []})
            query = parse_qs(urlsplit(url).query)
            day = query["d"][0]
            league_id = query["l"][0]
            if (league_id == str(SD_BD["epl"])
                    and day in ("2026-10-08", "2026-10-07")):
                return Response({"events": [{
                    "idEvent": day + "-final",
                    "idLeague": league_id,
                    "strHomeTeam": "Arsenal",
                    "strAwayTeam": "Chelsea",
                    "strTimestamp": day + "T19:00:00Z",
                    "strStatus": "Match Finished",
                    "intHomeScore": "2", "intAwayScore": "1",
                }]})
            return Response({"events": []})

        report = collect(now=NOW, keys={}, requester=requester)
        self.assertEqual(len(seen), 48)
        day_requests = [url for url in seen if "eventsday.php" in url]
        self.assertEqual(len(day_requests), 36)
        by_day = [
            parse_qs(urlsplit(day_requests[i]).query)["d"][0]
            for i in range(0, len(day_requests), len(LEAGUES))
        ]
        self.assertEqual(by_day, [
            "2026-10-09", "2026-10-08", "2026-10-07",
            "2026-10-10", "2026-10-11", "2026-10-12",
        ])
        finished = [row for row in report["sampled_fixtures"]
                    if row["status"] == "FINISHED"]
        self.assertEqual(len(finished), 2)
        self.assertTrue(all(row["score_ft"] == [2, 1] for row in finished))
        self.assertEqual(report["providers"][0]["recent_final_score_observations"], 2)
        self.assertFalse(report["six_league_independent_results_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_rate_limit_at_eleventh_call_preserves_recent_final_opportunity(self):
        from urllib.parse import parse_qs, urlsplit
        seen = []
        def requester(req, timeout):
            url = req.full_url
            seen.append(url)
            if len(seen) == 11:
                raise HTTPError(url, 429, "rate limited", {}, None)
            query = parse_qs(urlsplit(url).query)
            if query.get("d") == ["2026-10-08"] and query.get("l") == [str(SD_BD["epl"])]:
                return Response({"events": [{
                    "idEvent": "prior-day-final", "idLeague": str(SD_BD["epl"]),
                    "strHomeTeam": "Arsenal", "strAwayTeam": "Chelsea",
                    "strTimestamp": "2026-10-08T19:00:00Z",
                    "strStatus": "Match Finished", "intHomeScore": "2", "intAwayScore": "1",
                }]})
            return Response({"events": []})
        report = collect(now=NOW, keys={}, requester=requester)
        self.assertEqual(len(seen), 11)
        self.assertTrue(all("eventsday.php" in url for url in seen))
        self.assertEqual(report["providers"][0]["calls_attempted"], 11)
        self.assertIn("RATE_LIMITED", report["providers"][0]["warnings"])
        self.assertEqual(report["providers"][0]["recent_final_score_observations"], 1)
        self.assertFalse(report["six_league_independent_results_verified"])
        self.assertFalse(report["coverage_is_complete"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_nonfinal_recent_fixture_never_promoted_to_score_evidence(self):
        from urllib.parse import parse_qs, urlsplit

        def requester(req, timeout):
            url = req.full_url
            query = parse_qs(urlsplit(url).query)
            if ("eventsday.php" in url
                    and query.get("d") == ["2026-10-08"]
                    and query.get("l") == [str(SD_BD["epl"])]):
                return Response({"events": [{
                    "idEvent": "pending",
                    "idLeague": str(SD_BD["epl"]),
                    "strHomeTeam": "Arsenal", "strAwayTeam": "Chelsea",
                    "strTimestamp": "2026-10-08T20:00:00Z",
                    "strStatus": "Scheduled",
                    "intHomeScore": "2", "intAwayScore": "1",
                }]})
            return Response({"events": []})

        report = collect(now=NOW, keys={}, requester=requester)
        self.assertEqual(report["providers"][0]["recent_final_score_observations"], 0)
        self.assertEqual(report["sampled_fixtures"][0]["score_ft"], None)

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
        # Inspect provider fixture content only: generated UTC microseconds\n        # can coincidentally contain 9999 without any leaked bookmaker odds.\n        fixtures = json.dumps(result["sampled_fixtures"])\n        self.assertNotIn("9999", fixtures)\n        self.assertNotIn("bookmaker", fixtures)
        self.assertFalse(result["original_api_payload_redistributed"])


if __name__=="__main__":
    unittest.main()
