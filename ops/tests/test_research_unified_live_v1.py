import copy
import unittest
from ops.research_unified_live_v1 import forecast, audit_change, paired_metrics

NOW="2026-11-27T09:06:00Z"
def fixture():
    def record(i):
        return dict(event_id="synthetic",source="source"+str(i),origin="origin"+str(i),
                    updated="2026-11-27T09:05:45Z",captured="2026-11-27T09:05:50Z")
    score=[dict(record(i),home=1,away=0,home_red=0,away_red=0,minute=25,
                phase="1H",lineup_id="lineup",last_material_event="2026-11-27T08:45:00Z") for i in (1,2)]
    stats=[dict(record(i),phase="1H",lineup_id="lineup",window_start="2026-11-27T08:55:45Z",
                window_end="2026-11-27T09:05:45Z",home_npxg=.3,away_npxg=.1) for i in (3,4)]
    quote=dict(record(5),in_play=True,scope="full_match",suspended=False,bookmaker="synthetic",
               home=1,away=0,home_red=0,away_red=0,lineup_id="lineup",market="handicap",
               selection="home",line_convention="home_signed",line=-.25,decimal_odds=1.9)
    s=dict(event_id="synthetic",kickoff="2026-11-27T08:40:00Z",last_material_event="2026-11-27T08:45:00Z",
           score=score,stats=stats,quote=quote)
    p=dict(event_id="synthetic",frozen_at="2026-11-27T08:00:00Z",home_xg=1.47,away_xg=1.29)
    return s,p

class UnifiedLiveTests(unittest.TestCase):
    def test_distribution_and_settlement(self):
        s,p=fixture(); r=forecast(s,p,as_of=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["certified_ev"])
        self.assertAlmostEqual(sum(r["dynamic"][k] for k in ("home","draw","away")),1)
        self.assertAlmostEqual(sum(r["hypothetical_ev"]["settlement"].values()),1)
        self.assertTrue(all(h>=1 for _,h,a in r["dynamic"]["scores"]))
    def test_invalid_inputs(self):
        for field,value in [("origin","origin1"),("home",2),("home_red",1),("phase","2H"),("minute",24),("lineup_id","other"),("updated","2026-11-27T09:00:00Z"),("captured","2026-11-27T09:07:00Z")]:
            with self.subTest(field=field):
                s,p=fixture(); s["score"][1][field]=value
                r=forecast(s,p,as_of=NOW); self.assertNotIn("dynamic",r)
                self.assertEqual(r["status"],"HOLD")
    def test_xg_disagreement(self):
        s,p=fixture(); s["stats"][1]["home_npxg"]=1.5
        r=forecast(s,p,as_of=NOW); self.assertNotIn("dynamic",r); self.assertIn("baseline",r)
    def test_quote_block(self):
        for field,value in [("suspended",True),("scope","remaining"),("line_convention","away_signed"),("home",0),("updated","2026-11-27T08:44:00Z")]:
            with self.subTest(field=field):
                s,p=fixture(); s["quote"][field]=value
                self.assertNotIn("hypothetical_ev",forecast(s,p,as_of=NOW))
    def test_prior_leakage(self):
        s,p=fixture(); p["frozen_at"]=NOW
        self.assertNotIn("baseline",forecast(s,p,as_of=NOW))
    def test_red_scenario(self):
        s,p=fixture(); normal=forecast(s,p,as_of=NOW)["dynamic"]["home"]
        for x in s["score"]: x["home_red"]=1
        s["quote"]["home_red"]=1
        self.assertLess(forecast(s,p,as_of=NOW)["dynamic"]["home"],normal)
    def test_audit_decomposition(self):
        s,p=fixture(); old=forecast(s,p,as_of=NOW)
        for x in s["score"]: x["minute"]=26
        new=forecast(s,p,as_of=NOW)
        audit=audit_change(old,new)
        for v in audit.values(): self.assertAlmostEqual(v["clock_only"]+v["dynamic_increment_change"],v["total"])
        new["prior_signature"]=("different",)
        with self.assertRaises(ValueError): audit_change(old,new)
    def test_metrics_and_leakage(self):
        r=dict(event_id="synthetic",train_cutoff="2026-11-26T00:00:00Z",kickoff="2026-11-27T08:40:00Z",
               forecast_at=NOW,result_at="2026-11-27T10:40:00Z",baseline=dict(home=.5,draw=.3,away=.2),
               challenger=dict(home=.6,draw=.2,away=.2),outcome="home")
        self.assertLess(paired_metrics([r])["delta_brier"],0)
        self.assertFalse(paired_metrics([r])["certified_oos"])
        with self.assertRaises(ValueError): paired_metrics([r,r])
        r["train_cutoff"]=NOW
        with self.assertRaises(ValueError): paired_metrics([r])
    def test_stress(self):
        for h in range(4):
            for a in range(4):
                for rh in range(3):
                    for ra in range(3):
                        s,p=fixture()
                        for x in s["score"]+[s["quote"]]: x.update(home=h,away=a,home_red=rh,away_red=ra)
                        r=forecast(s,p,as_of=NOW)
                        self.assertEqual(r["status"],"HOLD")
                        self.assertAlmostEqual(sum(r["dynamic"][k] for k in ("home","draw","away")),1)
                        self.assertFalse(r["certified_ev"])
