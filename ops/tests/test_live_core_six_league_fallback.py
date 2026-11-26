import unittest
from datetime import datetime,timedelta,timezone
from live_core_football_data_schedule import project,collect,review
from live_core_calendar_fallback import inspect,probe
class SixLeagueFallbackTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.row={"id":1,"competition":{"code":"PL"},"status":"TIMED","utcDate":"2026-11-27T19:30:00Z","homeTeam":{"name":"Arsenal"},"awayTeam":{"name":"Chelsea"},"score":{"fullTime":{"home":None,"away":None}}}
    def test_strict_timed_and_duplicate(self):
        for x,reason in ((dict(self.row,status="SCHEDULED"),"STATUS_NOT_TIMED"),(dict(self.row,utcDate="2026-11-27T19:30:00"),"INVALID_UTC"),(dict(self.row,competition={"code":"PD"}),"COMPETITION_MISMATCH")):
            self.assertEqual(project("epl",{"matches":[x]},self.now)[1],{reason:1})
        self.assertEqual(project("epl",{"matches":[self.row,self.row]},self.now)[1],{"DUPLICATE_ID":2})
    def test_token_required_and_quota_stop(self):
        def bomb(*a):self.fail("network called")
        self.assertEqual(collect(["epl"],token="",fetcher=bomb,now=lambda:self.now)[1]["requests_attempted"],0)
        r=collect(["epl","laliga"],token="fake",fetcher=lambda *a:(None,"RATE_LIMITED"),now=lambda:self.now,pause=lambda _:None)[1]
        self.assertEqual(r["requests_attempted"],1);self.assertEqual(r["unrequested_leagues"],["laliga"])
    def test_exact_market_match_no_authentication(self):
        rows,_=project("epl",{"matches":[self.row]},self.now)
        m=dict(rows[0],oldest_market_update_utc=self.now.isoformat())
        r=review([m],rows,finished=self.now)
        self.assertEqual(r["local_agreements"],1);self.assertEqual(r["authenticated_forward_samples"],0)
        self.assertEqual(review([m],rows,finished=self.now+timedelta(minutes=21))["local_agreements"],0)
    def test_calendar_no_utc(self):
        row={"date":"2026-11-27","time":"19:30","team1":"Arsenal","team2":"Chelsea"}
        r=inspect("epl",{"matches":[row,dict(row,date="2026-11-28",score={"ft":[0,0]})]},self.now.date())
        self.assertEqual(r["calendar_candidates"],1);self.assertEqual(r["precise_utc_fixtures"],0)
        self.assertEqual(inspect("epl",{"matches":[row,row]},self.now.date())["calendar_candidates"],0)
    def test_public_five_requests(self):
        calls=[]
        def get(url):calls.append(url);return {"matches":[]}
        r=probe(getter=get,now=lambda:self.now)
        self.assertEqual(len(calls),5);self.assertEqual(r["authenticated_forward_samples"],0)
