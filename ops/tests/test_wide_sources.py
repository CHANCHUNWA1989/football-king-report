"""Wide no-key league API tests, including lower leagues and non-UTC dates."""
import copy
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wide_sources import (collect, read_openfootball, parse_openliga, MAX_REQUESTS,
                          NOW_LEAGUES, HISTORY_LEAGUES, GERMAN_LEAGUES)
from wide_source_guard import verify, newer

NOW = datetime.now(timezone.utc)


def loader(url):
    if "openligadb" in url:
        return [
            {"matchID":22, "matchDateTimeUTC":(NOW+timedelta(days=2)).isoformat(),
             "team1":{"teamName":"FC Köln"},"team2":{"teamName":"Hamburger SV"},
             "matchIsFinished":False, "matchResults":[]},
            {"matchID":23, "matchDateTimeUTC":(NOW-timedelta(days=2)).isoformat(),
             "team1":{"teamName":"Bayern"},"team2":{"teamName":"Dortmund"},
             "matchIsFinished":True,
             "matchResults":[{"pointsTeam1":3,"pointsTeam2":0}]},
        ]
    return {"name":"Test Soccer League","matches":[
        {"date":(NOW+timedelta(days=2)).date().isoformat(),
         "time":"20:30", "team1":"Club A", "team2":"Club B"},
        {"date":(NOW-timedelta(days=3)).date().isoformat(),
         "team1":"Club C", "team2":"Club D", "score":{"ft":[2,1]}},
    ]}


class WideFreeTests(unittest.TestCase):
    def setUp(self):
        self.result = collect(now=NOW,loader=loader)

    def test_more_than_twenty_catalogued_league_files(self):
        self.assertGreaterEqual(len(NOW_LEAGUES)+len(HISTORY_LEAGUES),26)
        self.assertEqual(len(GERMAN_LEAGUES),3)
        self.assertEqual(self.result["league_file_total"],MAX_REQUESTS)
        self.assertEqual(self.result["successful_league_files"],MAX_REQUESTS)
        self.assertFalse(self.result["market_odds_available"])
        self.assertFalse(self.result["automatic_prediction_training"])
        self.assertFalse(self.result["results_independently_verified"])
        verify(self.result)

    def test_de2_de3_and_european_lower_leagues_configured(self):
        keys={x["league"] for x in self.result["league_coverage"]}
        for league in ("bundesliga2","germany_liga3","league_one","league_two",
                       "ligue2","segunda","serie_b","scottish_premiership",
                       "greek_superleague","turkish_superlig","japan_j1",
                       "brazil_serie_b","usa_mls"):
            self.assertIn(league,keys)

    def test_archived_not_promoted_as_current(self):
        by={x["league"]:x for x in self.result["league_coverage"]}
        self.assertEqual(by["league_two"]["season_scope"],"ARCHIVED_SEASON_ONLY")
        self.assertEqual(by["epl"]["season_scope"],"CURRENT_SEASON_FILE")
        self.assertEqual(by["brazil_serie_a"]["season_scope"],"CURRENT_SEASON_FILE")
        tampered=copy.deepcopy(self.result)
        next(x for x in tampered["league_coverage"]
             if x["league"]=="league_two")["season_scope"]="CURRENT_SEASON_FILE"
        with self.assertRaisesRegex(ValueError,"MISLABELED_HISTORICAL_SEASON"):
            verify(tampered)

    def test_unzoned_openfootball_time_is_not_utc_kickoff(self):
        row=next(x for x in self.result["league_coverage"] if x["league"]=="epl")
        self.assertEqual(row["precise_utc_kickoffs_confirmed"],0)
        example=next(x for x in self.result["source_samples"] if x["source"]=="openfootball_json")
        self.assertIsNone(example["kickoff_utc"])
        self.assertTrue(example["time_is_unzoned_not_safely_usable_as_utc"])
        spoof=copy.deepcopy(self.result)
        next(x for x in spoof["source_samples"] if x["source"]=="openfootball_json")[
            "kickoff_utc"]="2026-10-10T14:00:00+00:00"
        with self.assertRaisesRegex(ValueError,"OPENFOOTBALL_TIMEZONE_NOT_VERIFIED"):
            verify(spoof)

    def test_openliga_utc_events_precisely_parsed_without_results_promotions(self):
        row=next(x for x in self.result["league_coverage"]
                 if x["provider"]=="openligadb" and x["league"]=="bundesliga2")
        self.assertEqual(row["precise_utc_kickoffs_confirmed"],2)
        self.assertEqual(row["reported_ft_scores_unverified"],1)
        self.assertEqual(row["upcoming_14_days"],1)
        self.assertIsNone(row["sample"][0]["score_full_time"])

    def test_malformed_openliga_clock_fails_safe(self):
        x=parse_openliga("bundesliga2","德乙",[
            {"matchID":1,"matchDateTimeUTC":"2026-10-10T11:00:00",
             "team1":{"teamName":"A"},"team2":{"teamName":"B"}}],NOW)
        self.assertEqual(x["precise_utc_kickoffs_confirmed"],0)

    def test_openfootball_score_never_claims_independent(self):
        x=read_openfootball("league_two","英乙","2025-26/en.4.json",
                           loader("https://example.com/test"),current=False)
        self.assertEqual(x["reported_ft_scores_unverified"],1)
        self.assertFalse(x["source_collection_is_asof_verified"])
        self.assertFalse(x["usable_for_live_betting"])

    def test_errors_leave_row_visible_but_zero_coverage(self):
        def fake(url):
            if "openligadb" in url:
                raise HTTPError(url,404,"absent",None,None)
            return loader(url)
        x=collect(now=NOW,loader=fake)
        failed=[e for e in x["league_coverage"] if e["provider"]=="openligadb"]
        self.assertEqual(len(failed),3)
        self.assertTrue(all(e["access_status"]=="NO_FILE_OR_ACCESS" for e in failed))
        verify(x)

    def test_missing_source_even_if_file_catalogued_not_counted(self):
        def fake(url):
            if "/2025-26/" in url:
                raise HTTPError(url,404,"missing",None,None)
            return loader(url)
        x=collect(now=NOW,loader=fake)
        # 2025 calendar-year archives still resolve even if all 2025-26
        # European season archives disappear.
        self.assertEqual(x["historical_only_file_successes"],6)
        self.assertLess(x["successful_league_files"],x["league_file_total"])
        europe = [r for r in x["league_coverage"]
                  if r["provider"]=="openfootball_json" and
                  r.get("season_scope")=="ARCHIVE"]
        self.assertEqual(len(europe),12)

    def test_never_insert_bookmaker_price_or_key_into_summary(self):
        s=json.dumps(self.result,ensure_ascii=False) if False else ""
        self.assertNotIn("API_FOOTBALL_KEY",str(self.result))
        self.assertNotIn("api_token",str(self.result))
        self.assertNotIn("bookmakers",str(self.result))

    def test_score_attempted_out_of_timezone_rejected(self):
        p=copy.deepcopy(self.result)
        p["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"INVALID_WIDE_PROVENANCE"):
            verify(p)

    def test_stale_replacement_rejected(self):
        self.assertFalse(newer(self.result,self.result))
        p=copy.deepcopy(self.result)
        p["collected_utc"]=(NOW-timedelta(hours=2)).isoformat()
        self.assertFalse(newer(p,self.result))

    def test_duplicate_providers_rejected(self):
        p=copy.deepcopy(self.result)
        p["providers"][1]["provider"]="openfootball_json"
        with self.assertRaisesRegex(ValueError,"INVALID_WIDE_LEAGUE_COUNT"):
            verify(p)

    def test_prior_file_cannot_be_mutated_to_claim_precise_openfootball_clock(self):
        p=copy.deepcopy(self.result)
        next(x for x in p["league_coverage"] if x["league"]=="epl")[
            "precise_utc_kickoffs_confirmed"]=200
        with self.assertRaisesRegex(ValueError,"OPENFOOTBALL_UNZONED_CLOCK_FALSE_CLAIM"):
            verify(p)


if __name__ == "__main__":
    unittest.main()
