"""BSD licensed free-market comparison remains isolated from primary suggestions."""
import sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bsd_overlay import build
from bsd_free import collect

NOW=datetime(2026,10,9,10,tzinfo=timezone.utc)
KO=(NOW+timedelta(days=2)).isoformat()
LAST=(NOW-timedelta(minutes=25)).isoformat()

class Resp:
    def __init__(self,data):
        import json
        self.bytes=json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n):return self.bytes[:n]

def api(req,timeout):
    if "/leagues/" in req.full_url:
        return Resp({"results":[{"id":80,"name":"Bundesliga","country":"Germany"}]})
    if "/events/" in req.full_url:
        return Resp({"results":[{"id":12345,"league_id":80,
                                  "home_team":"Bayern Munich","away_team":"Dortmund",
                                  "status":"upcoming","start_time":KO}]})
    return Resp({"results":[{
        "event_id":12345,"market":"1x2","outcome":x,
        "decimal_odds":val,"bookmaker_slug":"consensus","updated_at":LAST}
        for x,val in (("HOME",1.7),("DRAW",3.9),("AWAY",5.7))]})

class BSDOverlayTests(unittest.TestCase):
    def setUp(self):
        self.shadow={"status":"SHADOW_ONLY",
                     "as_of_utc":NOW.isoformat(),
                     "production_recommendations":"DISABLED",
                     "predictions":[{"event_id":"sample-999","league":"bundesliga",
                        "home":"Bayern Munich","away":"Dortmund",
                        "kickoff_utc":KO,"prediction_utc":NOW.isoformat(),
                        "p_home":0.62,"p_draw":0.22,"p_away":0.16,
                        "production_recommendations":"DISABLED"}]}

    def test_no_secret_has_explicit_hold(self):
        bsd=collect(now=NOW,token="")
        o=build(self.shadow,bsd,now=NOW)
        self.assertEqual(o["status"],"HOLD")
        self.assertEqual(o["source_state"],"NOT_CONFIGURED")
        self.assertEqual(o["time_valid_shadow_pairs"],0)
        self.assertFalse(o["automatic_replacement_of_main_market"])

    def test_free_consensus_parallels_same_frozen_forecast(self):
        bsd=collect(now=NOW,token="test-secret",client=api)
        o=build(self.shadow,bsd,now=NOW)
        self.assertEqual(o["status"],"RESEARCH_ONLY")
        self.assertEqual(o["time_valid_shadow_pairs"],1)
        self.assertTrue(o["compared_to_primary_model"])
        self.assertFalse(o["real_money_recommendations"])
        self.assertFalse(o["market_is_executable"])
        self.assertEqual(o["production_recommendations"],"DISABLED")

    def test_wrong_teams_does_not_create_market_pair(self):
        self.shadow["predictions"][0]["away"]="Schalke"
        bsd=collect(now=NOW,token="test-secret",client=api)
        o=build(self.shadow,bsd,now=NOW)
        self.assertEqual(o["time_valid_shadow_pairs"],0)
        self.assertEqual(o["status"],"HOLD")

    def test_stale_market_is_hold(self):
        bsd=collect(now=NOW,token="test-secret",client=api)
        o=build(self.shadow,bsd,now=NOW+timedelta(hours=20))
        self.assertEqual(o["status"],"HOLD")

    def test_no_changing_shadow_or_production_status(self):
        bsd=collect(now=NOW,token="test-secret",client=api)
        self.shadow["production_recommendations"]="ENABLED"
        o=build(self.shadow,bsd,now=NOW)
        self.assertEqual(o["status"],"HOLD")
        self.assertFalse(o["automatic_replacement_of_main_market"])

if __name__=="__main__":unittest.main()
