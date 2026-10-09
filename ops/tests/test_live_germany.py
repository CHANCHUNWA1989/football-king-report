"""No-key OpenLigaDB matchday: independent score states, no false live claims."""
import copy
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_germany import collect, parse, iso, API_BASE, SHORTCUTS
from live_germany_guard import verify, publication

NOW=datetime.now(timezone.utc)
KO=(NOW+timedelta(hours=4)).isoformat()
FINISH=(NOW-timedelta(hours=4)).isoformat()


def entry(shortcut="bl1", kickoff=KO, finished=False):
    return {
        "leagueShortcut":shortcut,"matchID":777,
        "matchDateTimeUTC":kickoff,
        "team1":{"teamName":"FC Bayern München"},
        "team2":{"teamName":"Borussia Dortmund"},
        "matchIsFinished":finished,
        "matchResults":[
            {"resultTypeID":1,"pointsTeam1":0,"pointsTeam2":1},
            {"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}] if finished else [],
    }


class LiveGermanTests(unittest.TestCase):
    def test_german_leagues_bounded(self):
        self.assertEqual(set(SHORTCUTS),{"bundesliga","bundesliga2","germany_liga3"})
        self.assertEqual(SHORTCUTS["bundesliga"],"bl1")

    def test_only_finished_fulltime_score_is_used(self):
        p=parse("bundesliga",[entry(finished=True,kickoff=FINISH)],NOW)
        self.assertEqual(len(p),1)
        self.assertEqual(p[0]["score_ft"],[2,1])
        self.assertEqual(p[0]["status"],"FINISHED_CONFIRMED_BY_SOURCE")

    def test_halftime_only_not_falsely_a_final(self):
        raw=entry(finished=True,kickoff=FINISH)
        raw["matchResults"]=[{"resultTypeID":1,"pointsTeam1":2,"pointsTeam2":0}]
        p=parse("bundesliga",[raw],NOW)
        self.assertIsNone(p[0]["score_ft"])
        self.assertEqual(p[0]["status"],"FINISHED_SCORE_PENDING")

    def test_in_progress_no_minute_or_score_fabricated(self):
        x=entry(kickoff=(NOW-timedelta(minutes=25)).isoformat())
        p=parse("bundesliga",[x],NOW)
        self.assertEqual(p[0]["status"],"STARTED_STATUS_UNCONFIRMED")
        self.assertIsNone(p[0]["score_ft"])
        self.assertNotIn("live_minute",p[0])

    def test_foreign_league_blocked(self):
        self.assertEqual(parse("bundesliga",[entry(shortcut="bl2")],NOW),[])

    def test_timezone_field_may_be_utc_without_z(self):
        s=KO.replace("+00:00","")
        self.assertEqual(iso(s).utcoffset(),timedelta(0))

    def test_collect_three_bounded_calls_no_key(self):
        calls=[]
        def fake(url):
            calls.append(url)
            return [entry(shortcut=url.rsplit("/",1)[-1])]
        report=collect(now=NOW,getter=fake)
        self.assertEqual(len(calls),3)
        self.assertEqual(report["calls_attempted"],3)
        self.assertEqual(len(report["matches"]),3)
        self.assertFalse(report["live_second_by_second_guaranteed"])
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertTrue(all(url.startswith(API_BASE) for url in calls))
        verify(report)

    def test_empty_matchday_is_not_any_verified_live_result(self):
        r=collect(now=NOW,getter=lambda url:[])
        self.assertEqual(r["status"],"RESEARCH_ONLY")
        self.assertEqual(len(r["matches"]),0)
        self.assertTrue(all(v["status"]=="EMPTY_CURRENT_MATCHDAY" for v in r["league_coverage"]))

    def test_all_network_failed_is_hold_not_success(self):
        def fail(url): raise ValueError("bad response")
        r=collect(now=NOW,getter=fail)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["matches"],[])
        verify(r)

    def test_publishing_cannot_invent_score(self):
        p=collect(now=NOW,getter=lambda url:[entry(shortcut=url.rsplit("/",1)[-1])])
        p["matches"][0]["score_ft"]=[99,99]
        with self.assertRaisesRegex(ValueError,"FAKE_FINISHED_SCORE"):
            verify(p)

    def test_no_raw_bookmaker_prices_allowed(self):
        p=collect(now=NOW,getter=lambda url:[])
        p["matches"].append({
            "league":"bundesliga","home":"Home","away":"Away",
            "provider_match_id":9,"kickoff_utc":KO,"status":"SCHEDULED",
            "score_ft":None,"odds":2.5})
        with self.assertRaisesRegex(ValueError,"RAW_OR_UNAUTHORIZED_LIVE_FIELDS"):
            verify(p)

    def test_no_fake_live_or_betting_unlock(self):
        p=collect(now=NOW,getter=lambda url:[])
        p["live_second_by_second_guaranteed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_LIVE_RESEARCH_STATE"):
            verify(p)
        p["live_second_by_second_guaranteed"]=False
        p["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_LIVE_RESEARCH_STATE"):
            verify(p)

    def test_stale_snapshots_rejected(self):
        p=collect(now=NOW,getter=lambda url:[])
        p["collected_utc"]=(NOW-timedelta(hours=2)).isoformat()
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE"):
            verify(p)

    def test_same_snapshot_does_not_overwrite(self):
        p=collect(now=NOW,getter=lambda url:[])
        self.assertFalse(publication(p,p))


if __name__=="__main__":
    unittest.main()
