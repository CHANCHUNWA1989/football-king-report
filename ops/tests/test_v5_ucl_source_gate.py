import copy
import unittest
from datetime import datetime,timezone
from ops.v5_ucl_source_gate import gate,parse_fd,parse_ts,crosswalk

NOW=datetime(2026,11,25,13,tzinfo=timezone.utc)
F={"competition":{"code":"CL"},"matches":[{"id":1,"competition":{"code":"CL"},"status":"TIMED","utcDate":"2026-11-25T20:00:00Z","homeTeam":{"id":11},"awayTeam":{"id":12},"score":{"winner":None,"fullTime":{"home":None,"away":None}}}]}
S={"events":[{"idLeague":"4480","strSport":"Soccer","strStatus":"Not Started","idEvent":"2","idHomeTeam":"21","idAwayTeam":"22","strTimestamp":"2026-11-25T20:00:00","intHomeScore":None,"intAwayScore":None}]}
M={"schema":"v5-ucl-native-id-crosswalk-v1","pairs":[{"football_data_team_id":11,"sportsdb_team_id":21,"evidence_reference":"https://example.invalid/test"},{"football_data_team_id":12,"sportsdb_team_id":22,"evidence_reference":"https://example.invalid/test"}]}
def wrap(x,t="2026-11-25T12:59:00Z"):return {"captured_utc":t,"payload":x}
class GateTest(unittest.TestCase):
    def test_candidate_not_qualified(self):
        r=gate(wrap(F),wrap(S),M,NOW)
        self.assertEqual(r["candidate_schedule_agreements"],1)
        self.assertEqual(r["eligible_model_inputs"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_missing_and_stale(self):
        for f in (None,wrap(F,"2026-11-25T11:00:00Z"),wrap(F,"2026-11-25T13:01:00Z")):
            self.assertEqual(gate(f,wrap(S),M,NOW)["candidate_schedule_agreements"],0)
    def test_clock_conflict(self):
        s=copy.deepcopy(S);s["events"][0]["strTimestamp"]="2026-11-25T20:01:00"
        self.assertEqual(gate(wrap(F),wrap(s),M,NOW)["candidate_schedule_agreements"],0)
    def test_crosswalk_collision(self):
        m=copy.deepcopy(M);m["pairs"][1]["sportsdb_team_id"]=21
        with self.assertRaises(ValueError):crosswalk(m)
    def test_duplicate_event_and_result(self):
        f=copy.deepcopy(F);f["matches"].append(f["matches"][0])
        with self.assertRaises(ValueError):parse_fd(f)
        f=copy.deepcopy(F);f["matches"][0]["score"]["fullTime"]["home"]=1
        with self.assertRaises(ValueError):parse_fd(f)
    def test_wrong_competition(self):
        f=copy.deepcopy(F);f["competition"]["code"]="PL"
        with self.assertRaises(ValueError):parse_fd(f)
        s=copy.deepcopy(S);s["events"][0]["idLeague"]="9999"
        self.assertEqual(parse_ts(s),[])
