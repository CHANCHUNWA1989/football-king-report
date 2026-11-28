import copy
import json
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from ops.research_unified_execution_v41 import run
from ops.research_unified_prematch_audit_v34 import Forecast
from ops.research_market_provenance_v1 import Quote
from ops.research_unified_prematch_replay_v35 import freeze
from ops.research_snapshot_replay_v3 import capture
from ops.tests.test_research_prematch_live_bridge_v4 import case

ROOT=Path(__file__).resolve().parents[2]

def fixture():
    args=case()
    raw=json.loads(args["prematch_raw"])
    frozen=datetime.fromisoformat(raw["as_of"].replace("Z","+00:00"))
    kick=datetime.fromisoformat(raw["kickoff"].replace("Z","+00:00"))
    h,a=raw["rates"]
    eid=raw["fixture_id"]
    observed=datetime.fromisoformat(raw["rates_at"].replace("Z","+00:00"))
    fs=[Forecast(eid,kick,observed,"m0","f0",h,a),
        Forecast(eid,kick,observed,"m1","f1",h+.1,a)]
    qs=[Quote("p"+str(i),"book",eid,m,s,l,1.9,frozen,kick,
              upstream_provider="u"+str(i))
        for m,s,l in [("handicap","home",-.25),("handicap","away",-.25),
                      ("totals","over",2.75),("totals","under",2.75)]
        for i in range(2)]
    r=freeze(event_id=eid,kickoff=kick,now=frozen,forecasts=fs,quotes=qs,
             handicap_line=-.25,totals_line=2.75,root=ROOT)
    return dict(roster={eid:raw["kickoff"]},records=[r],cutoff=raw["as_of"],
                live_cases={eid:{"model":"m0","inputs":args}},
                live_as_of=args["as_of"],model_release=args["model_release"],root=ROOT)

class UnifiedExecutionTests(unittest.TestCase):
    def assert_hold(self,r):
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("source_identity_authenticated","external_timestamp_verified",
                  "training_admission","qualified_for_production",
                  "verified_executable_ev","independent_oos_proven",
                  "cross_path_market_equality_verified"):
            self.assertIs(r[k],False)
    def rejected(self,kwargs):
        r=run(**kwargs)
        self.assert_hold(r)
        self.assertFalse(r["execution_passed"])
        self.assertNotIn("live_research",r)
        self.assertNotIn("local_execution_sha256",r)
    def test_end_to_end(self):
        kw=fixture()
        r=run(**kw)
        self.assert_hold(r)
        self.assertTrue(r["execution_passed"],r)
        self.assertEqual(r["prematch_fixture_count"],1)
        self.assertEqual(r["live_fixture_count"],1)
        live=r["live_research"]["synthetic"]
        self.assertAlmostEqual(sum(live["dynamic"][k] for k in ("home","draw","away")),1)
        self.assertEqual(r,run(**kw))
    def test_batch_only(self):
        kw=fixture()
        for k in ("live_cases","live_as_of","model_release"):del kw[k]
        r=run(**kw)
        self.assert_hold(r)
        self.assertTrue(r["execution_passed"])
        self.assertEqual(r["not_requested_live_count"],1)
    def test_missing_batch(self):
        kw=fixture();kw["records"]=[]
        self.rejected(kw)
    def test_other_event(self):
        kw=fixture();kw["live_cases"]["unknown"]=kw["live_cases"].pop("synthetic")
        self.rejected(kw)
    def test_wrong_model(self):
        for model in ("m1","missing"):
            kw=fixture();kw["live_cases"]["synthetic"]["model"]=model
            self.rejected(kw)
    def test_clock_or_release_mismatch(self):
        for field,value in (("model_release","other"),("live_as_of","2026-11-27T09:05:59Z")):
            kw=fixture();kw[field]=value
            self.rejected(kw)
    def test_receipt_tamper(self):
        kw=fixture()
        kw["live_cases"]["synthetic"]["inputs"]["prematch_receipt"]["status"]="READY"
        self.rejected(kw)
    def test_frozen_batch_tamper(self):
        kw=fixture()
        kw["records"][0]["forecasts"][0]["home"]=9
        self.rejected(kw)
    def test_red_card_sensitivity(self):
        kw=fixture()
        base=run(**kw)
        args=kw["live_cases"]["synthetic"]["inputs"]
        rows=[json.loads(raw) for raw in args["live_raw_captures"]]
        for row in rows:
            if row["kind"]=="score":row["payload"]["home_red"]=1
        args["live_raw_captures"]=[json.dumps(row).encode() for row in rows]
        red=run(**kw)
        self.assert_hold(red)
        self.assertTrue(red["execution_passed"],red)
        self.assertLess(red["live_research"]["synthetic"]["dynamic"]["home"],
                        base["live_research"]["synthetic"]["dynamic"]["home"])
    def test_conflicting_red_cards(self):
        kw=fixture()
        args=kw["live_cases"]["synthetic"]["inputs"]
        rows=[json.loads(raw) for raw in args["live_raw_captures"]]
        next(r for r in rows if r["kind"]=="score")["payload"]["home_red"]=1
        args["live_raw_captures"]=[json.dumps(row).encode() for row in rows]
        self.rejected(kw)
if __name__=="__main__":unittest.main()
