import unittest
from datetime import datetime,timedelta,timezone
from live_core_same_batch_collection import schedule_diagnostic
from live_core_openliga_schedule_smoke import inspect,probe
class ScheduleDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.ko=(self.now+timedelta(days=1)).isoformat()
        self.row={"idLeague":"4331","idEvent":"7","strHomeTeam":"Werder Bremen","strAwayTeam":"Mainz","strTimestamp":self.ko,"strStatus":"Not Started"}
        self.ol={"leagueShortcut":"bl1","matchIsFinished":False,"matchResults":[],"matchDateTimeUTC":self.ko,
                 "team1":{"teamName":"Werder Bremen"},"team2":{"teamName":"Mainz"},"matchID":1}
    def test_status_diagnosis_and_limit(self):
        for update,reason in (({"strStatus":None},"STATUS_MISSING"),({"strStatus":"Live"},"STATUS_NOT_EXPLICIT_SCHEDULED"),({"intHomeScore":0},"SCORE_PRESENT"),({"strTimestamp":"2026-11-27T12:00:00"},"KICKOFF_MISSING_INVALID_OR_NAIVE")):
            rows,d=schedule_diagnostic({"events":[dict(self.row,**update),self.row]},"bundesliga",self.now)
            self.assertEqual(rows,[]);self.assertEqual(d["disposition"],{reason:1})
            self.assertEqual(d["not_inspected_free_limit"],1)
        rows,d=schedule_diagnostic({"events":[self.row]},"bundesliga",self.now)
        self.assertEqual(len(rows),1);self.assertEqual(d["disposition"],{"ACCEPTED_LOCAL":1})
    def test_missing_shape_and_empty_distinct(self):
        with self.assertRaises(ValueError):schedule_diagnostic({},"bundesliga",self.now)
        self.assertEqual(schedule_diagnostic({"events":None},"bundesliga",self.now)[1]["inspected_rows"],0)
    def test_openliga_duplicate_and_status(self):
        d=inspect([self.ol,self.ol,dict(self.ol,matchID=2,matchIsFinished=None)],self.now)
        self.assertEqual(d["local_scheduled_rows"],0)
        self.assertEqual(d["disposition"],{"FINISHED_OR_STATUS_UNKNOWN":1,"DUPLICATE_CANDIDATE":2})
    def test_openliga_one_request_counts_only(self):
        calls=[]
        def get(url):calls.append(url);return [self.ol]
        r=probe(getter=get,now=lambda:self.now)
        self.assertEqual(len(calls),1);self.assertEqual(r["schedule_diagnostic"]["local_scheduled_rows"],1)
        self.assertNotIn("Werder",str(r));self.assertEqual(r["authenticated_forward_samples"],0)
