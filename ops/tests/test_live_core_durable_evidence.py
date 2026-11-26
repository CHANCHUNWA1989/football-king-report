import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_quota_sqlite_cas import SQLiteCAS
from vnext_quota_coordinator_contract import reserve_simulated,State
from live_core_sportmonks_capture import parse,dual_run
from live_core_event_revision import audit
from live_core_real_observations import epoch_iso


class QuotaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"quota.db"
        self.store=SQLiteCAS(self.path,"account1")
        self.store.initialize()

    def reserve(self,i):
        return reserve_simulated(SQLiteCAS(self.path,"account1"),epoch="account1",
            revision_floor=0,request_id="req"+str(i),consumer="worker",
            now=200000,observed=199999,daily_remaining=100,minute_remaining=10)

    def test_durable(self):
        self.assertTrue(self.reserve(1)["simulated_reservation"])
        self.assertEqual(SQLiteCAS(self.path,"account1").read().revision,1)
        self.assertFalse(self.reserve(1)["simulated_reservation"])

    def test_concurrent_limit(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(self.reserve,range(30)))
        n=sum(r["simulated_reservation"] for r in results)
        self.assertGreater(n,0)
        self.assertLessEqual(n,9)
        self.assertEqual(self.store.read().revision,n)
        self.assertTrue(all(not r["real_request_authorized"] for r in results))

    def test_no_reinitialize(self):
        with self.assertRaises(FileExistsError): self.store.initialize()

    def test_epoch_mismatch(self):
        with self.assertRaises(ValueError): SQLiteCAS(self.path,"account2").read()

    def test_non_append(self):
        old=self.store.read()
        with self.assertRaises(ValueError): self.store.cas(old,State("account1",1,1,()))

    def test_cas_conflict(self):
        old=self.store.read()
        self.assertTrue(self.reserve(1)["simulated_reservation"])
        self.assertFalse(self.store.cas(old,State("account1",1,200000,(("other","worker",200000),))))


class DualTests(unittest.TestCase):
    def setUp(self):
        self.now=1795680240
        self.ko=self.now-3600
        self.clock=dict(captured=self.now-4,received=self.now-3,observed_claim=self.now-5)
        self.mapping=dict(fixture_id="test-match",provider_id=70,home_id=10,away_id=20,kickoff_epoch=self.ko)
        self.row=dict(id=70,starting_at_timestamp=self.ko,state_id=6,
            participants=[dict(id=i,meta=dict(location=s)) for i,s in ((10,"home"),(20,"away"))],
            periods=[dict(type_id=2,ticking=True,minutes=45)],
            scores=[dict(description="CURRENT",participant_id=i,score=dict(participant=s,goals=0))
                for i,s in ((10,"home"),(20,"away"))],
            events=[dict(id=90,type_id=20,participant_id=10,player_id=91,minute=11,extra_minute=None)])
        self.pm=dict(fixture_id="test-match",provider_id=7,home_id=1,away_id=2,kickoff_utc=epoch_iso(self.ko))
        self.primary=dict(errors=[],response=[dict(fixture=dict(id=7,date=epoch_iso(self.ko),status=dict(short="2H",elapsed=45,extra=None)),
            teams=dict(home=dict(id=1),away=dict(id=2)),goals=dict(home=0,away=0),
            events=[dict(type="Card",detail="Red Card",team=dict(id=1),player=dict(id=8),time=dict(elapsed=11))])])
        self.prior=dict(fixture_id="test-match",model_id="test-prior",
            forecast_utc=epoch_iso(self.ko-900),inputs_available_utc=epoch_iso(self.ko-1000),
            expected_home_goals=1.3,expected_away_goals=1.1,input_sha256="c"*64,
            production_recommendations="DISABLED",calibrated=False)

    def raw(self):
        return json.dumps(dict(data=self.row)).encode()

    def parse(self):
        return parse(self.raw(),self.mapping,now=self.now,**self.clock)

    def replay(self):
        return dual_run(json.dumps(self.primary).encode(),self.pm,self.raw(),self.mapping,
            primary_clock=self.clock,secondary_clock=self.clock,now=self.now,prematch=self.prior,
            markets=[dict(market="totals",side="UNDER",line=2.25)])

    def test_both_raw(self):
        r=self.replay()
        self.assertTrue(r["two_raw_payloads_parsed"])
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["source_independence_verified"])
        self.assertFalse(r["positive_ev_verified"])

    def test_conflicting_cards(self):
        self.row["events"]=[]
        self.assertNotIn("probabilities_1x2",self.replay())

    def test_missing_events(self):
        del self.row["events"]
        self.assertNotIn("probabilities_1x2",self.replay())

    def test_var(self):
        self.row["events"].append(dict(id=99,type_id=10))
        self.assertNotIn("probabilities_1x2",self.replay())

    def test_kickoff_mismatch(self):
        self.mapping["kickoff_epoch"]+=1
        self.assertNotIn("probabilities_1x2",self.replay())

    def test_correction_review(self):
        a=self.parse()
        b=dict(state={**a["state"],"origin":"other"},url="https://example.org/match",payload_sha256="d"*64)
        prior={**a["state"],"red_home":2,"observed":self.now-20,"received":self.now-19}
        r=audit(prior,a,b,self.now)
        self.assertEqual(r["correction_fields"],["red_home"])
        self.assertFalse(r["auto_resume_allowed"])
        self.assertFalse(r["previous_forecast_rewrite_allowed"])
