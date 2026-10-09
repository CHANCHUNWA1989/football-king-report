"""No-key worldwide league overlay should be safe even before its first run."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wide_overlay import build
from wide_sources import collect


class WideMobileOverlayTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        def fake(url):
            if "openligadb" in url:
                return [{
                    "matchID":1,
                    "matchDateTimeUTC":(self.now+timedelta(days=2)).isoformat(),
                    "team1":{"teamName":"Home"},"team2":{"teamName":"Away"},
                    "matchIsFinished":False
                }]
            return {"matches":[{"team1":"Home","team2":"Away",
                                "date":"2026-10-10","time":"18:30"}]}
        self.a=collect(now=self.now,loader=fake)

    def test_no_snapshot_remains_hold_without_losing_league_directory(self):
        b=build(None,now=self.now)
        self.assertEqual(b["status"],"HOLD")
        self.assertEqual(b["league_file_total"],30)
        self.assertEqual(len(b["league_cards"]),30)
        self.assertFalse(b["provider_market_odds_available"])
        self.assertFalse(b["historic_data_can_be_presented_as_live"])

    def test_all_sources_present_but_not_counted_as_verified_predictions(self):
        b=build(self.a,now=self.now)
        self.assertEqual(b["status"],"RESEARCH_ONLY")
        self.assertEqual(b["source_count"],2)
        self.assertEqual(b["successful_league_files"],30)
        self.assertEqual(b["current_season_file_successes"],9)
        self.assertEqual(b["historical_only_file_successes"],18)
        self.assertGreaterEqual(b["precise_german_utc_kickoffs_observed"],3)
        self.assertFalse(b["training_evidence_validated"])
        self.assertFalse(b["provider_market_odds_available"])

    def test_archived_small_leagues_are_explicit(self):
        b=build(self.a,now=self.now)
        smaller=next(x for x in b["league_cards"] if x["id"]=="league_two")
        self.assertTrue(smaller["historical_only"])
        self.assertEqual(smaller["season_scope"],"ARCHIVED_SEASON_ONLY")
        self.assertEqual(smaller["precise_utc_kickoffs_confirmed"],0)

    def test_german_small_league_precise_utc_backups_remain_schedule_only(self):
        result=build(self.a,now=self.now)
        matches=result["backup_scheduled_fixtures"]
        self.assertGreaterEqual(len(matches),3)
        self.assertTrue(all(m["backup_for_schedule_only"] for m in matches))
        self.assertTrue(all(m["market_confirmed"] is False for m in matches))
        self.assertTrue(all(m["betting_recommendation"] is False for m in matches))
        self.assertTrue(all(m["production_recommendations"]=="DISABLED" for m in matches))

    def test_stale_data_not_published_as_current(self):
        now=self.now+timedelta(hours=49)
        b=build(self.a,now=now)
        self.assertEqual(b["status"],"HOLD")
        self.assertEqual(b["successful_league_files"],0)

    def test_fake_market_odds_cannot_enter_overlay(self):
        item=copy.deepcopy(self.a)
        item["market_odds_available"]=True
        b=build(item,now=self.now)
        self.assertEqual(b["status"],"HOLD")
        self.assertEqual(b["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
