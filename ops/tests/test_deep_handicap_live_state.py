"""Synthetic live-state projection checks; not actual match data."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_live_state import analyze


def inputs():
    f={"gender":"men","league":"epl","home_id":"test-home","away_id":"test-away",
       "kickoff_utc":"2026-11-27T08:00:00Z","expected_identity_sealed_utc":"2026-11-27T07:00:00Z",
       "provider_event_ids":{"fotmob":"synthetic1","skysports":"synthetic2"},
       "provider_event_urls":{"fotmob":"https://www.fotmob.com/matches/synthetic1",
                              "skysports":"https://www.skysports.com/football/synthetic2"}}
    obs=[]
    for provider in f["provider_event_ids"]:
        obs.append({**{k:f[k] for k in ("gender","league","home_id","away_id","kickoff_utc")},
            "provider":provider,"source_event_id":f["provider_event_ids"][provider],
            "source_url":f["provider_event_urls"][provider],"captured_utc":"2026-11-27T09:15:10Z",
            "source_updated_utc":"2026-11-27T09:15:00Z","match_status":"SECOND_HALF",
            "score_home":2,"score_away":0,"regulation_minute_elapsed":60,
            "home_red_cards":0,"away_red_cards":0})
    return f,obs


def run(f,obs,**kwargs):
    args=dict(as_of_utc="2026-11-27T09:15:20Z",home_rate=2.9,away_rate=.9,
              side="HOME",handicap=-2.25,total_line=3.25)
    args.update(kwargs)
    return analyze(f,obs,**args)


class DeepLiveTests(unittest.TestCase):
    def test_nine_scenarios_all_share_final_score_projection(self):
        f,obs=inputs()
        out=run(f,obs)
        self.assertEqual(out["scenario_count"],9)
        self.assertEqual(out["status"],"HOLD")
        self.assertFalse(out["red_card_event_authenticated"])
        self.assertFalse(out["qualifies_for_betting"])
        for s in out["scenarios"]:
            self.assertAlmostEqual(s["score_mass"],1)
            for key in ("one_x_two","handicap","over","under"):
                self.assertAlmostEqual(sum(s[key].values()),1)
            self.assertTrue(all(r["home"]>=2 and r["away"]>=0 for r in s["top_scores"]))
            self.assertFalse(s["actual_market_lines_verified"])

    def test_card_effect_direction_and_pace(self):
        f,obs=inputs()
        base=run(f,obs)
        h=copy.deepcopy(obs)
        a=copy.deepcopy(obs)
        for o in h:
            o["home_red_cards"]=1
        for o in a:
            o["away_red_cards"]=1
        home,away=run(f,h),run(f,a)
        for b,x,y in zip(base["scenarios"],home["scenarios"],away["scenarios"]):
            self.assertLessEqual(x["handicap"]["FULL_WIN"],b["handicap"]["FULL_WIN"]+1e-10)
            self.assertGreaterEqual(y["handicap"]["FULL_WIN"],b["handicap"]["FULL_WIN"]-1e-10)
        self.assertLess(base["scenarios"][0]["remaining_home_goal_rate"],
                        base["scenarios"][2]["remaining_home_goal_rate"])

    def test_disagreement_missing_stale_and_unsupported_rejected(self):
        for change in (
            lambda x:x[0].update(home_red_cards=1),
            lambda x:x[0].pop("away_red_cards"),
            lambda x:x[0].update(regulation_minute_elapsed=61),
            lambda x:x[0].update(source_updated_utc="2026-11-27T09:12:00Z"),
            lambda x:x[0].update(score_away=1),
            lambda x:[o.update(regulation_minute_elapsed=90) for o in x],
            lambda x:[o.update(home_red_cards=True) for o in x],
            lambda x:[o.update(regulation_minute_elapsed=20) for o in x],
        ):
            f,obs=inputs()
            change(obs)
            self.assertEqual(run(f,obs)["scenarios"],[])

    def test_remaining_time_shrinks_rate_and_home_away_mirror(self):
        f,obs=inputs()
        base=run(f,obs)
        for o in obs:
            o.update(regulation_minute_elapsed=80,captured_utc="2026-11-27T09:35:10Z",
                     source_updated_utc="2026-11-27T09:35:00Z")
        later=run(f,obs,as_of_utc="2026-11-27T09:35:20Z")
        self.assertLess(later["scenarios"][0]["remaining_home_goal_rate"],
                        base["scenarios"][0]["remaining_home_goal_rate"])
        f,obs=inputs()
        f["home_id"],f["away_id"]=f["away_id"],f["home_id"]
        for o in obs:
            o.update(home_id=f["home_id"],away_id=f["away_id"],score_home=0,score_away=2)
        mirror=run(f,obs,home_rate=.9,away_rate=2.9,side="AWAY")
        for b,m in zip(base["scenarios"],mirror["scenarios"]):
            self.assertAlmostEqual(b["handicap"]["FULL_WIN"],m["handicap"]["FULL_WIN"])

    def test_648_synthetic_state_scenarios(self):
        count=0
        for minute in (55,70,85):
            for h,a in ((0,0),(1,0),(2,0),(0,1)):
                for hr,ar in ((0,0),(1,0),(0,1),(1,1),(2,0),(0,2)):
                    f,obs=inputs()
                    from datetime import datetime,timedelta,timezone
                    now=datetime(2026,11,27,8,tzinfo=timezone.utc)+timedelta(minutes=minute+15)
                    for o in obs:
                        o.update(regulation_minute_elapsed=minute,score_home=h,score_away=a,
                                 home_red_cards=hr,away_red_cards=ar,
                                 captured_utc=now.isoformat(),source_updated_utc=now.isoformat())
                    out=run(f,obs,as_of_utc=now.isoformat())
                    self.assertEqual(out["scenario_count"],9)
                    self.assertTrue(all(abs(v["score_mass"]-1)<1e-9 for v in out["scenarios"]))
                    count+=out["scenario_count"]
        self.assertEqual(count,648)
