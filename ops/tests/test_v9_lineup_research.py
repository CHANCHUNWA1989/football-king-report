import unittest,json
from datetime import datetime,timezone
from ops.v9_lineup_research import side,adjust,load,sha,build
NOW=datetime(2026,11,26,tzinfo=timezone.utc)
F=datetime(2026,11,25,18,30,tzinfo=timezone.utc)
K=datetime(2026,11,25,19,tzinfo=timezone.utc)
def team(t,start):
    ids=list(range(start,start+12))
    return {"team_id":t,"lineup_status":"CONFIRMED","lineup_published_utc":"2026-11-25T18:00:00Z",
        "lineup_captured_utc":"2026-11-25T18:05:00Z","expected_xi_utc":"2026-11-25T12:00:00Z",
        "expected_xi":ids[:11],"confirmed_xi":ids[1:],
        "ratings":[{"player_id":i,"team_id":t,"available_utc":"2026-11-25T10:00:00Z","rating":.5 if i==ids[-1] else 0} for i in ids],
        "absences":[{"player_id":ids[0],"team_id":t,"reported_utc":"2026-11-25T17:00:00Z","status":"CONFIRMED_UNAVAILABLE"}]}
def capture():
    return {"match_id":1,"kickoff_utc":K.isoformat(),"forecast_utc":F.isoformat(),"result_available_utc":"2026-11-25T22:00:00Z",
        "phase":"REGULATION","status":"FINISHED","home":team(2,100),"away":team(3,200),"home_goals":2,"away_goals":0,
        "baseline_probability":[.5,.3,.2],"baseline_conditioned_on_confirmed_xi":False}
def inputs(r):
    raw=json.dumps({"schema":"v9-3-lineup-research-cases-v1","provider":"synthetic","rating_definition":"test","matches":[r]}).encode()
    return raw,{"schema":"v9-3-authorized-lineup-receipt-v1","sha256":sha(raw),"provider":"synthetic","rating_definition":"test","authorization_reference":"unit test","captured_utc":NOW.isoformat()}
class LineupResearchTests(unittest.TestCase):
    def test_valid_unqualified(self):
        r=build(load(*inputs(capture()),NOW))
        self.assertEqual(r["paired_matches"],1);self.assertFalse(r["official_lineup_authenticated"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_late_rating(self):
        r=team(2,100);r["ratings"][0]["available_utc"]="2026-11-25T18:15:00Z"
        with self.assertRaisesRegex(ValueError,"AFTER_FORECAST"):side(r,F,K)
    def test_absence_conflict(self):
        r=team(2,100);r["absences"][0]["player_id"]=101
        with self.assertRaisesRegex(ValueError,"XI_ABSENCE_CONFLICT"):side(r,F,K)
    def test_missing_rating(self):
        r=team(2,100);r["ratings"].pop()
        with self.assertRaisesRegex(ValueError,"MISSING_PLAYER_RATING"):side(r,F,K)
    def test_direction(self):
        self.assertGreater(adjust([.5,.3,.2],.5)[0],.5)
        self.assertLess(adjust([.5,.3,.2],-.5)[0],.5)
    def test_baseline_double_count(self):
        r=capture();r["baseline_conditioned_on_confirmed_xi"]=True
        with self.assertRaisesRegex(ValueError,"BASELINE_SCOPE"):load(*inputs(r),NOW)
    def test_duplicate_xi(self):
        r=team(2,100);r["confirmed_xi"][0]=r["confirmed_xi"][1]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_PLAYER"):side(r,F,K)
