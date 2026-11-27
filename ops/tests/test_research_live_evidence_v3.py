import unittest
from copy import deepcopy
from ops.tests.test_research_unified_live_v2 import fixture, NOW
from ops.research_live_evidence_v3 import seal, verify_bundle, settle, evaluate
from ops.research_unified_live_v2 import digest

FIN="2026-11-27T10:35:00Z"
RELEASE="synthetic-v2"
def bundle():
    s,p=fixture()
    return seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE)
def final():
    return [dict(event_id="synthetic",source="source"+str(i),origin="origin"+str(i),
                 evidence_ref="synthetic:"+str(i),status="FT",scope="regulation",
                 finished_at="2026-11-27T10:30:00Z",updated="2026-11-27T10:31:00Z",
                 captured="2026-11-27T10:32:00Z",home=2,away=1) for i in (1,2)]
def evaluate_one(pairs):
    return evaluate(pairs,model_release=RELEASE,cohort_start="2026-11-27T00:00:00Z",
                    cohort_end="2026-11-27T10:00:00Z",as_of=FIN)
class LiveEvidenceTests(unittest.TestCase):
    def test_replay_and_tamper(self):
        b=bundle(); self.assertTrue(verify_bundle(b))
        b["report"]["dynamic"]["home"]=0
        self.assertFalse(verify_bundle(b))
        b["sha256"]=digest({k:v for k,v in b.items() if k!="sha256"})
        self.assertFalse(verify_bundle(b))
    def test_copy(self):
        s,p=fixture(); b=seal(s,p,as_of=NOW,captured_at=NOW,model_release=RELEASE)
        s["score"][0]["home"]=3
        self.assertTrue(verify_bundle(b))
    def test_clock(self):
        s,p=fixture()
        with self.assertRaises(ValueError): seal(s,p,as_of=NOW,captured_at=FIN,model_release=RELEASE)
    def test_final(self):
        r=settle(bundle(),final(),as_of=FIN)
        self.assertEqual(r["outcome"],"home")
        self.assertFalse(r["source_authenticity_verified"])
    def test_conflict(self):
        for field,value in [("origin","origin1"),("home",3),("scope","extra_time"),
                            ("finished_at",NOW),("captured","2026-11-27T11:00:00Z")]:
            with self.subTest(field=field):
                f=final(); f[1][field]=value
                with self.assertRaises(ValueError): settle(bundle(),f,as_of=FIN)
    def test_score_correction(self):
        f=final()
        for r in f:r["home"]=0
        with self.assertRaises(ValueError): settle(bundle(),f,as_of=FIN)
    def test_metrics(self):
        b=bundle(); r=settle(b,final(),as_of=FIN); e=evaluate_one([(b,r)])
        self.assertEqual(e["n"],1)
        self.assertFalse(e["independent_oos_proven"])
        self.assertIsNone(e["metrics"]["descriptive_cluster_bootstrap_ci95"])
        for label in ("baseline","dynamic"):
            for key in ("home","draw","away"):
                self.assertEqual(sum(x["count"] for x in e["reliability"][label][key]),1)
        with self.assertRaises(ValueError): evaluate_one([(b,r),(b,r)])
        r["outcome"]="away"
        with self.assertRaises(ValueError): evaluate_one([(b,r)])
