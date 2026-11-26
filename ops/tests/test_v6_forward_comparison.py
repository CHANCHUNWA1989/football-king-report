import unittest
from datetime import datetime,timezone,timedelta
from ops.v6_forward_comparison import seal,score
NOW=datetime(2026,11,25,15,tzinfo=timezone.utc)
KO=NOW+timedelta(days=2)
def inputs():
    b={"schema":"v6-unified-forward-shadow-v1","status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0,"generated_utc":NOW.isoformat(),"predictions":[
        {"league":"bundesliga","provider_event_id":"1","home_native_id":"2","away_native_id":"3","kickoff_utc":KO.isoformat(),
        "prediction_utc":NOW.isoformat(),"source_receipts":[{"captured_utc":NOW.isoformat()}],"ensemble_1x2":[.5,.3,.2],"production_recommendations":"DISABLED"}]}
    c={"schema":"v6-1-league-calibration-research-v1","status":"HOLD","production_recommendations":"DISABLED","automatic_promotion":False,"prospective_validation":False,"cutoff":"2026-01-01","per_league":{"de.1":{"params":[1.,0.,0.]}}}
    return b,c
def result():
    return [{"leagueShortcut":"bl1","leagueSeason":2026,"leagueId":1,"matchID":1,"team1":{"teamId":2,"teamName":"H"},"team2":{"teamId":3,"teamName":"A"},"matchDateTimeUTC":KO.isoformat(),"matchIsFinished":True,"matchResults":[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]}]
class ForwardComparisonTests(unittest.TestCase):
    def test_seal_and_score(self):
        r=seal(*inputs(),NOW)
        self.assertEqual(len(r["rows"]),1)
        s=score(r,result(),KO+timedelta(hours=3))
        self.assertEqual(s["n"],1)
        self.assertEqual(s["baseline"]["correct"],1)
        self.assertEqual(s["verified_forward_sample_credit"],0)
    def test_stale_bundle(self):
        with self.assertRaisesRegex(ValueError,"STALE"):seal(*inputs(),NOW+timedelta(minutes=11))
    def test_late_seal(self):
        b,c=inputs();b["predictions"][0]["kickoff_utc"]=(NOW+timedelta(minutes=5)).isoformat()
        with self.assertRaisesRegex(ValueError,"CLOCK"):seal(b,c,NOW)
    def test_identity_conflict(self):
        r=seal(*inputs(),NOW);x=result();x[0]["team2"]["teamId"]=4
        with self.assertRaisesRegex(ValueError,"IDENTITY"):score(r,x,KO+timedelta(hours=3))
    def test_tampered_candidate(self):
        r=seal(*inputs(),NOW);r["rows"][0]["candidate"]=[1,0,0]
        with self.assertRaisesRegex(ValueError,"MISMATCH"):score(r,result(),KO+timedelta(hours=3))
    def test_other_leagues_excluded(self):
        b,c=inputs();b["predictions"][0]["league"]="bundesliga2"
        self.assertEqual(seal(b,c,NOW)["rows"],[])
