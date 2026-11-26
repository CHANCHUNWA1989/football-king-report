import unittest
from datetime import datetime,timezone,timedelta
from ops.v8_ucl_current_intake import build,fd_diagnostics,ts_diagnostics,season_at
NOW=datetime(2026,11,25,17,20,tzinfo=timezone.utc)
def cap(payload):
    return {"captured_utc":NOW.isoformat(),"sha256":"a"*64,"payload":payload}
def fdrow():
    return {"id":1,"competition":{"code":"CL"},"season":{"startDate":"2026-09-01"},"stage":"LEAGUE_STAGE","matchday":5,
        "homeTeam":{"id":2},"awayTeam":{"id":3},"utcDate":"2026-11-25T20:00:00Z","status":"TIMED","score":{"winner":None,"fullTime":{"home":None,"away":None}}}
class CurrentIntakeTests(unittest.TestCase):
    def test_partial_fd(self):
        r=fd_diagnostics(cap({"competition":{"code":"CL"},"matches":[fdrow()]}),NOW,2026)
        self.assertEqual(r["future_within_48h"],1);self.assertFalse(r["complete_phase_schedule"])
    def test_future_final_rejected(self):
        r=fdrow();r["status"]="FINISHED";r["score"]={"duration":"REGULAR","fullTime":{"home":2,"away":1}}
        with self.assertRaisesRegex(ValueError,"UNSAFE_FINAL"):fd_diagnostics(cap({"competition":{"code":"CL"},"matches":[r]}),NOW,2026)
    def test_result_bearing_fixture(self):
        r=fdrow();r["score"]["fullTime"]["home"]=1
        with self.assertRaisesRegex(ValueError,"RESULT_BEARING"):fd_diagnostics(cap({"competition":{"code":"CL"},"matches":[r]}),NOW,2026)
    def test_partial_ts(self):
        r=ts_diagnostics(cap({"events":[{"idLeague":"4480","strSport":"Soccer","strSeason":"2026-2027","idEvent":"1"}]}),NOW,2026)
        self.assertEqual(r["returned_rows"],1);self.assertFalse(r["complete_phase_schedule"])
    def test_stale(self):
        r=cap({"events":[]});r["captured_utc"]=(NOW-timedelta(minutes=16)).isoformat()
        self.assertEqual(build(None,r,None,NOW)["providers"]["thesportsdb_season"]["status"],"HOLD_INVALID_OR_STALE")
    def test_hold_even_with_source(self):
        r=build(cap({"competition":{"code":"CL"},"matches":[fdrow()]}),None,None,NOW)
        self.assertEqual(r["current_fixture_forecasts"],0);self.assertFalse(r["current_training_ready"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
