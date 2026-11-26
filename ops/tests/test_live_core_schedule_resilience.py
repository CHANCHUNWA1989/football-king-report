import unittest
from datetime import datetime,timedelta,timezone
from live_core_schedule_resilience import route_batch
from live_core_same_batch_collection import collect_schedules
from live_core_german_schedule_corroboration import schedule_only
class ScheduleResilienceTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.row={"league":"bundesliga","home_id":"a","away_id":"b","native_id":"1","kickoff_utc":(self.now+timedelta(days=1)).isoformat(),"received_utc":self.now.isoformat()}
    def attempt(self,league="bundesliga",status="HTTP_ERROR",n=0):
        return {"league":league,"response_status":status,"received_utc":self.now.isoformat(),"accepted_rows":n,"diagnostic":None}
    def route(self,s,o,a):
        g={"requests_attempted":1,"schedule_diagnostic":{"local_scheduled_rows":len(o)}} if o else None
        return route_batch([],s,o,a,len(a),g,finished=self.now)
    def test_fallback_does_not_claim_agreement(self):
        d=self.route([], [self.row],[self.attempt()])
        self.assertEqual(d["by_league"]["bundesliga"]["route"],"OPENLIGA_FALLBACK_SCHEDULE_ONLY")
        self.assertEqual(d["authenticated_forward_samples"],0)
    def test_two_sources_not_identity_match(self):
        d=self.route([self.row],[dict(self.row,home_id="c")],[self.attempt(status="OK",n=1)])
        self.assertEqual(d["by_league"]["bundesliga"]["route"],"BOTH_SOURCES_AVAILABLE_NOT_CORROBORATED")
    def test_stop_accounts_for_unrequested_leagues(self):
        attempts=[]
        rows,n,_=collect_schedules(fetcher=lambda *a:(None,"RATE_LIMITED"),now=lambda:self.now,pause=lambda _:None,attempt_sink=attempts)
        d=route_batch([],rows,[],attempts,n,None,finished=self.now)
        self.assertEqual(n,1);self.assertTrue(d["provider_stop_observed"])
        self.assertEqual(d["by_league"]["bundesliga"]["sportsdb_attempt_status"],"NOT_REQUESTED_AFTER_PROVIDER_STOP")
        with self.assertRaises(ValueError):self.route([],[],attempts+[self.attempt()])
    def test_stale_and_missing_attempt_rejected(self):
        old=dict(self.row,received_utc=(self.now-timedelta(minutes=21)).isoformat())
        self.assertEqual(self.route([], [old],[])["fresh_schedule_leagues"],0)
        with self.assertRaises(ValueError):self.route([self.row],[],[])
    def test_public_probe_fallback(self):
        def get(url):return [{"leagueShortcut":"bl1","matchID":1,"matchIsFinished":False,"matchResults":[],"matchDateTimeUTC":self.row["kickoff_utc"],"team1":{"teamName":"Mainz"},"team2":{"teamName":"Werder Bremen"}}]
        r=schedule_only(fetcher=lambda *a:(None,"HTTP_ERROR"),getter=get,now=lambda:self.now)
        self.assertEqual(r["schedule_resilience"]["by_league"]["bundesliga"]["route"],"OPENLIGA_FALLBACK_SCHEDULE_ONLY")
        self.assertIsNone(r["sportsdb_http_error_code"])
