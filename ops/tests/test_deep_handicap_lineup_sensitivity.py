"""Synthetic lineup sensitivity, chronology and identity regression tests."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_lineup_sensitivity import analyze
from deep_handicap_joint_score import project

NOW="2026-11-27T08:00:00Z"


def inputs():
    fixture={"league":"epl","home":"synthetic-home","away":"synthetic-away",
             "event_id":"synthetic-fixture","kickoff_utc":"2026-11-27T09:00:00Z"}
    f={**fixture,"prediction_utc":NOW,"production_recommendations":"DISABLED"}
    r={"fixture":copy.deepcopy(fixture),"player_id_namespace":"synthetic-provider",
       "kind":"PREDECLARED_REFERENCE_XI","recorded_utc":"2026-11-26T08:00:00Z",
       "home_starters":[f"h{i}" for i in range(11)],"away_starters":[f"a{i}" for i in range(11)]}
    l=copy.deepcopy(r)
    l.update(kind="OFFICIAL_STARTING_XI_CLAIM",published_utc="2026-11-27T07:55:00Z",
             captured_utc="2026-11-27T07:57:00Z",source_url="https://example.org/synthetic")
    return f,r,l


def run(f,r,l,**kwargs):
    args=dict(as_of_utc=NOW,home_rate=2.9,away_rate=.9,side="HOME",
              handicap=-2.25,total_line=3.25)
    args.update(kwargs)
    return analyze(f,r,l,**args)


class LineupSensitivityTests(unittest.TestCase):
    def test_no_changes_equals_baseline_and_not_authenticated(self):
        f,r,l=inputs()
        before=copy.deepcopy((f,r,l))
        result=run(f,r,l)
        self.assertEqual((f,r,l),before)
        self.assertEqual(result["scenario_count"],9)
        self.assertEqual(result["home_changes"],0)
        self.assertEqual(result["away_changes"],0)
        base=project(2.9,.9,"HOME",-2.25,3.25)
        for p in result["scenarios"]:
            self.assertEqual(p["handicap"],base["handicap"])
        self.assertEqual(result["status"],"HOLD")
        self.assertFalse(result["official_lineup_authenticated"])
        self.assertFalse(result["qualifies_for_betting"])
        self.assertFalse(result["baseline_roster_model_binding_verified"])
        self.assertNotIn("home_starters",json.dumps(result))

    def test_rotation_has_both_upside_and_downside(self):
        f,r,l=inputs()
        l["home_starters"][:3]=["new1","new2","new3"]
        out=run(f,r,l)
        self.assertEqual(out["home_changes"],3)
        self.assertEqual(out["away_changes"],0)
        b=project(2.9,.9,"HOME",-2.25,3.25)["handicap"]["FULL_WIN"]
        self.assertLess(out["full_win_envelope"]["min"],b)
        self.assertGreater(out["full_win_envelope"]["max"],b)
        for p in out["scenarios"]:
            self.assertAlmostEqual(sum(p["handicap"].values()),1)
            self.assertAlmostEqual(sum(p["over"].values()),1)

    def test_identity_time_and_lineup_claim_rejections(self):
        cases=[
            lambda f,r,l:l.update(kind="PREDICTED_XI"),
            lambda f,r,l:l.update(player_id_namespace="other"),
            lambda f,r,l:l["fixture"].update(event_id="other"),
            lambda f,r,l:l["home_starters"].__setitem__(0,"h1"),
            lambda f,r,l:l["home_starters"].__setitem__(0,"a0"),
            lambda f,r,l:l["home_starters"].__setitem__(0,True),
            lambda f,r,l:l.update(captured_utc="2026-11-27T08:01:00Z"),
            lambda f,r,l:r.update(recorded_utc="2026-11-27T07:56:00Z"),
            lambda f,r,l:r.update(recorded_utc="2026-11-01T07:56:00Z"),
            lambda f,r,l:l.update(source_url="http://example.org"),
            lambda f,r,l:f.update(score_ft=[2,0]),
        ]
        for change in cases:
            f,r,l=inputs()
            change(f,r,l)
            self.assertEqual(run(f,r,l)["scenarios"],[])
        f,r,l=inputs()
        self.assertEqual(run(f,r,l,as_of_utc="2026-11-27T08:01:00Z")["scenarios"],[])

    def test_out_of_domain_scenario_no_partial_results(self):
        f,r,l=inputs()
        l["home_starters"][0]="replacement"
        o=run(f,r,l,home_rate=5.5)
        self.assertEqual(o["scenarios"],[])
        self.assertNotIn("full_win_envelope",o)

    def test_home_away_symmetry(self):
        f,r,l=inputs()
        l["home_starters"][0]="replacement"
        base=run(f,r,l)
        for obj in (r,l):
            obj["home_starters"],obj["away_starters"]=obj["away_starters"],obj["home_starters"]
            fixture=obj["fixture"]
            fixture["home"],fixture["away"]=fixture["away"],fixture["home"]
        f["home"],f["away"]=f["away"],f["home"]
        mirror=run(f,r,l,home_rate=.9,away_rate=2.9,side="AWAY")
        for key in ("min","max"):
            self.assertAlmostEqual(base["full_win_envelope"][key],mirror["full_win_envelope"][key])

    def test_case_aliases_and_result_bearing_rosters_fail_closed(self):
        f,r,l=inputs()
        l["home_starters"][0]="H0"
        out=run(f,r,l)
        self.assertEqual(out["reason"],"AMBIGUOUS_PLAYER_ID_CASE")
        self.assertEqual(out["scenarios"],[])
        for which in ("reference","lineup"):
            f,r,l=inputs()
            (r if which=="reference" else l)["score_ft"]=[2,0]
            out=run(f,r,l)
            self.assertEqual(out["reason"],"RESULT_BEARING_ROSTER")
            self.assertEqual(out["scenarios"],[])
    def test_two_team_rotation_keeps_joint_probability_consistent(self):
        f,r,l=inputs()
        l["home_starters"][0]="new-home"
        l["away_starters"][0]="new-away"
        out=run(f,r,l)
        self.assertEqual((out["home_changes"],out["away_changes"]),(1,1))
        self.assertEqual(out["scenario_count"],9)
        for p in out["scenarios"]:
            self.assertAlmostEqual(sum(p["one_x_two"].values()),1)
            for grade,values in p["handicap_and_over_joint"].items():
                self.assertAlmostEqual(sum(values.values()),p["handicap"][grade])
        self.assertFalse(out["baseline_roster_model_binding_verified"])
