import hashlib
import json
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from ops.tests.test_research_archive_score_recovery_v14 import fixture
from ops.research_replay_readiness_v31 import readiness,from_root,SINGLE,DUAL

BASE=datetime(2026,11,1,12,tzinfo=timezone.utc)
NOW="2026-11-06T00:00:00Z"
def sample():
    raw,_=fixture();d=json.loads(raw);original=d["samples"][0]
    d["samples"]=[];d["n"]=3;d["checked_utc"]=NOW
    cases=[]
    for i in range(3):
        k=BASE+timedelta(hours=3*i)
        f=k-timedelta(hours=1)
        r=dict(original,key=json.dumps(["bundesliga","a","b",k.isoformat()]),
            kickoff_utc=k.isoformat(),forecast_utc=f.isoformat(),
            market_utc=(f-timedelta(minutes=5)).isoformat(),y=0)
        d["samples"].append(r)
        t=k+timedelta(hours=2)
        refs=[dict(provider="OpenLigaDB",captured_utc=t.isoformat(),
                   path="test",decoded_sha256="a"*64,provider_id=str(i+1))]
        state=SINGLE
        if i!=1:
            state=DUAL
            refs.append(dict(provider="thesportsdb",captured_utc=t.isoformat(),
                path="test2",decoded_sha256="b"*64,provider_id="s"+str(i)))
        cases.append(dict(key=r["key"],state=state,recorded_final_observation_utc=t.isoformat(),
            score_candidate=[2,1],references=refs,result_availability_authenticated=False,training_admission=False))
    raw=json.dumps(d).encode()
    return raw,dict(schema="recorded-final-observation-clock-v30",ledger_sha256=hashlib.sha256(raw).hexdigest(),
        status="HOLD",production_recommendations="DISABLED",training_admission=False,authenticated_samples=0,cases=cases)

class ReplayReadinessTests(unittest.TestCase):
    def test_exact_forecast_boundary(self):
        raw,p=sample();r=readiness(raw,p,as_of=NOW)
        self.assertEqual(r["scenarios"]["all_candidates"]["0"]["counts"]["at_least_one_prior"],1)
        self.assertEqual(r["scenarios"]["all_candidates"]["6"]["counts"]["at_least_one_prior"],0)
        self.assertEqual(r["scenarios"]["dual_only"]["0"]["target_count"],2)
        self.assertEqual(r["scenarios"]["dual_only"]["0"]["counts"]["at_least_one_prior"],1)
        self.assertFalse(r["training_admission"])
    def test_clock_must_match_refs(self):
        raw,p=sample();p["cases"][0]["recorded_final_observation_utc"]="2026-11-01T13:40:00Z"
        with self.assertRaises(ValueError):readiness(raw,p,as_of=NOW)
    def test_duplicate_publisher_rejected(self):
        raw,p=sample();p["cases"][0]["references"][1]["provider"]="OpenLigaDB"
        with self.assertRaises(ValueError):readiness(raw,p,as_of=NOW)
    def test_conflict_excluded(self):
        raw,p=sample();p["cases"][0]["state"]="FINAL_CLOCK_CONFLICT"
        r=readiness(raw,p,as_of=NOW)
        self.assertEqual(r["clock_candidates"],2)
        self.assertEqual(r["excluded_targets"]["NO_ACCEPTABLE_CLOCK"],1)
        self.assertEqual(r["scenarios"]["all_candidates"]["0"]["counts"]["at_least_one_prior"],0)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        self.assertEqual(raw,ledger.read_bytes())
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["weights_fitted"])
        for scope in r["scenarios"].values():
            self.assertGreaterEqual(scope["0"]["counts"].get("at_least_one_prior",0),scope["24"]["counts"].get("at_least_one_prior",0))
        print("V31_REPLAY_READINESS_SUMMARY "+json.dumps(r,sort_keys=True))
