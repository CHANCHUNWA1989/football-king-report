import unittest
from datetime import datetime,timedelta,timezone
from live_core_same_batch_collection import naive_utc_candidate,schedule_diagnostic
from live_core_german_schedule_corroboration import confirm_naive,schedule_only
class TimezoneCandidateTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.row={"idLeague":"4331","idEvent":"7","strHomeTeam":"Werder Bremen","strAwayTeam":"Mainz","strTimestamp":"2026-11-27T19:30:00","dateEvent":"2026-11-27","strTime":"19:30:00","strStatus":"Not Started"}
    def candidates(self,**kw):
        return naive_utc_candidate({"events":[dict(self.row,**kw)]},self.now)
    def test_legacy_stays_strict_and_research_candidate(self):
        rows,d=schedule_diagnostic({"events":[self.row]},"bundesliga",self.now)
        self.assertEqual(rows,[]);self.assertEqual(d["disposition"],{"KICKOFF_NAIVE":1})
        c,reason=self.candidates();self.assertEqual(reason,"UTC_CANDIDATE_NOT_ATTESTED")
        self.assertEqual(c[0]["kickoff_utc"],"2026-11-27T19:30:00+00:00")
    def test_missing_conflicting_and_midnight(self):
        for change,reason in (({"strTime":None},"UTC_FIELDS_MISSING"),({"strTime":"20:30:00"},"UTC_FIELDS_CONFLICT"),({"strTimestamp":"2026-11-27T00:00:00","strTime":"00:00:00"},"MIDNIGHT_PLACEHOLDER_RISK")):
            rows,r=self.candidates(**change);self.assertEqual(rows,[]);self.assertEqual(r,reason)
    def test_exact_independent_namespace_required(self):
        c,_=self.candidates()
        for rows,reason in (([],"NO_OPENLIGA_TEAM_MATCH"),([dict(c[0],kickoff_utc="2026-11-27T20:30:00+00:00")],"KICKOFF_CONFLICT"),(c+c,"AMBIGUOUS_OPENLIGA")):
            out,r=confirm_naive(c,rows,finished=self.now);self.assertEqual(out,[]);self.assertEqual(r["disposition"],{reason:1})
        out,r=confirm_naive(c,c,finished=self.now)
        self.assertEqual(len(out),1);self.assertEqual(r["authenticated_forward_samples"],0)
    def test_stale_and_started(self):
        c,_=self.candidates()
        self.assertEqual(confirm_naive(c,c,finished=self.now+timedelta(minutes=21))[1]["locally_corroborated"],0)
    def test_public_pair_injected(self):
        def fetch(*a):return {"events":[self.row]},"OK"
        def get(url):return [{"leagueShortcut":"bl1","matchID":1,"matchIsFinished":False,"matchResults":[],"matchDateTimeUTC":"2026-11-27T19:30:00Z","team1":{"teamName":"Werder Bremen"},"team2":{"teamName":"Mainz"}}]
        r=schedule_only(fetcher=fetch,getter=get,now=lambda:self.now)
        self.assertEqual(r["sportsdb_local_rows"],0);self.assertEqual(r["timezone_candidate_review"]["locally_corroborated"],1)
        self.assertEqual(r["authenticated_forward_samples"],0);self.assertNotIn("Werder",str(r))

    def test_candidate_diagnostics_do_not_change_strict_population(self):
        from live_core_same_batch_collection import collect_schedules
        sink=[];details={};rows_diag={};candidate_diag={}
        def fetch(*a):
            return ({"events":[self.row]} if "id=4331" in a[1] else {"events":[]}),"OK"
        rows,n,failures=collect_schedules(fetcher=fetch,now=lambda:self.now,
                pause=lambda _:None,diagnostics=details,row_diagnostics=rows_diag,
                naive_sink=sink,candidate_diagnostic=candidate_diag)
        self.assertEqual(n,6)
        self.assertEqual(rows,[])
        self.assertEqual(len(sink),1)
        self.assertEqual(details["bundesliga"],"NO_ELIGIBLE_FIRST_EVENT")
        self.assertEqual(rows_diag["bundesliga"]["disposition"],{"KICKOFF_NAIVE":1})
        self.assertEqual(candidate_diag["reason"],"UTC_CANDIDATE_NOT_ATTESTED")
        self.assertEqual(failures,{"EMPTY_SCHEDULE_RESPONSE":5,"KICKOFF_NAIVE":1})
