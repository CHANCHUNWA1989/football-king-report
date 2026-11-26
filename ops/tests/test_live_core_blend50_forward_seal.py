import copy
import unittest
from datetime import datetime,timedelta,timezone
from live_core_blend50_forward_seal import seal,PROTOCOL,digest,prior_rates
from live_core_opponent_strength import forecasts
class Blend50ForwardSealTests(unittest.TestCase):
    def fixture(self):
        now=datetime(2026,12,1,10,tzinfo=timezone.utc)
        ko=now+timedelta(hours=2)
        history=[]
        for i in range(60):
            day=now-timedelta(days=70-i)
            history.append({"league":"EPL","match_id":str(i),"home":"A","away":"B","kickoff_utc":day.isoformat(),
                            "observed_utc":(day+timedelta(hours=3)).isoformat(),"score":[i%3,1],"status":"FINAL_REGULATION"})
        sources=[{"provider":p,"fixture_id":"1","home":"A","away":"B","kickoff_utc":ko.isoformat(),
                  "observed_utc":now.isoformat(),"status":"SCHEDULED"} for p in ("provider_a","provider_b")]
        return now,{"protocol":PROTOCOL,"league":"EPL","fixture":{"home":"A","away":"B","kickoff_utc":ko.isoformat(),"sources":sources},"history":history}
    def test_seal_parity_and_no_authentication(self):
        now,d=self.fixture();r=seal(d,now=now)
        self.assertEqual(r["record_sha256"],digest(r["record"]))
        self.assertEqual(r,seal(d,now=now))
        self.assertEqual(r["record"]["authenticated_forward_samples"],0)
        rows=[(x["kickoff_utc"][:10],x["home"],x["away"],*x["score"]) for x in d["history"]]
        old=forecasts(rows,[("2026-12-01","A","B",0,0)])[0][-1]
        for name,v in r["record"]["models"].items():
            self.assertEqual(tuple(v["probabilities_1x2"]),old[name][0])
    def test_reject_fixture_outcome_and_provider_conflict(self):
        now,d=self.fixture();d["fixture"]["score"]=[0,0]
        with self.assertRaises(ValueError):seal(d,now=now)
        now,d=self.fixture();d["fixture"]["sources"][1]["provider"]="PROVIDER_A"
        with self.assertRaises(ValueError):seal(d,now=now)
    def test_reject_same_day_and_future_history(self):
        now,d=self.fixture()
        for key,value in (("kickoff_utc",now.isoformat()),("observed_utc",(now+timedelta(minutes=1)).isoformat())):
            x=copy.deepcopy(d);x["history"][-1][key]=value
            with self.assertRaises(ValueError):seal(x,now=now)
    def test_window_and_staleness(self):
        now,d=self.fixture()
        with self.assertRaises(ValueError):seal(d,now=now+timedelta(hours=2))
        d["fixture"]["sources"][0]["observed_utc"]=(now-timedelta(hours=7)).isoformat()
        with self.assertRaises(ValueError):seal(d,now=now)
    def test_duplicate_history(self):
        now,d=self.fixture();d["history"].append(copy.deepcopy(d["history"][0]))
        with self.assertRaises(ValueError):seal(d,now=now)
