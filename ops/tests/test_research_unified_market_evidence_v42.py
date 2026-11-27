import json
import unittest
from datetime import timedelta
from ops.tests.test_research_unified_execution_v41 import fixture as v41_fixture
from ops.research_snapshot_replay_v3 import capture
from ops.research_unified_cutoff_v39 import utc
from ops.research_unified_market_evidence_v42 import run

def replace_raw(kw,p):
    args=kw["live_cases"]["synthetic"]["inputs"]
    args["prematch_raw"]=json.dumps(p).encode()
    args["prematch_receipt"]=capture(args["prematch_raw"])

def fixture():
    kw=v41_fixture()
    p=json.loads(kw["live_cases"]["synthetic"]["inputs"]["prematch_raw"])
    quotes=kw["records"][0]["quotes"]
    for i,snap in enumerate(p["snapshots"]):
        rows=[q for q in quotes if q["source"]=="p"+str(i)]
        snap.update(publisher=rows[0]["source"],upstream=rows[0]["upstream_provider"],
                    bookmaker=rows[0]["bookmaker"],observed_at=rows[0]["observed_at"],
                    asian=[{k:q[k] for k in ("market","selection","line","decimal_odds")}
                           for q in rows])
    replace_raw(kw,p)
    return kw,p

class MarketEvidenceV42Tests(unittest.TestCase):
    def check(self,kw,ok):
        r=run(**kw)
        self.assertIs(r["execution_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        for k in ("source_identity_authenticated","external_timestamp_verified",
                  "training_admission","qualified_for_production","verified_executable_ev",
                  "independent_oos_proven","cross_path_market_equality_verified",
                  "cross_path_1x2_equality_verified"):
            self.assertIs(r[k],False)
        if not ok:
            self.assertNotIn("v41_execution",r)
            self.assertNotIn("local_execution_sha256",r)
        return r
    def test_exact_match(self):
        kw,p=fixture()
        r=self.check(kw,True)
        self.assertTrue(r["cross_path_asian_equality_verified"])
        self.assertEqual(r["matched_live_fixture_count"],1)
        self.assertEqual(len(r["asian_evidence_sha256"]["synthetic"]),64)
    def test_missing_asian_rows(self):
        kw,p=fixture()
        for s in p["snapshots"]:s["asian"]=[]
        replace_raw(kw,p)
        self.check(kw,False)
    def test_mismatched_prices(self):
        kw,p=fixture()
        for s in p["snapshots"]:
            for q in s["asian"]:q["decimal_odds"]=2.0
        replace_raw(kw,p)
        self.check(kw,False)
    def test_mismatched_lines(self):
        kw,p=fixture()
        for s in p["snapshots"]:
            for q in s["asian"]:
                if q["market"]=="handicap":q["line"]=-.5
        replace_raw(kw,p)
        self.check(kw,False)
    def test_mismatched_bookmaker(self):
        kw,p=fixture()
        for s in p["snapshots"]:s["bookmaker"]="other"
        replace_raw(kw,p)
        self.check(kw,False)
    def test_mismatched_lineage(self):
        for field in ("publisher","upstream"):
            kw,p=fixture()
            p["snapshots"][0][field]="other"
            replace_raw(kw,p)
            self.check(kw,False)
    def test_mismatched_timestamp(self):
        kw,p=fixture()
        for s in p["snapshots"]:
            s["observed_at"]=(utc(s["observed_at"])-timedelta(seconds=1)).isoformat()
        replace_raw(kw,p)
        self.check(kw,False)
    def test_order_invariance(self):
        kw,p=fixture()
        before=self.check(kw,True)["asian_evidence_sha256"]
        p["snapshots"].reverse()
        for s in p["snapshots"]:s["asian"].reverse()
        replace_raw(kw,p)
        self.assertEqual(before,self.check(kw,True)["asian_evidence_sha256"])
    def test_batch_only_no_claim(self):
        kw,p=fixture()
        for field in ("live_cases","live_as_of","model_release"):del kw[field]
        r=self.check(kw,True)
        self.assertFalse(r["cross_path_asian_equality_verified"])
        self.assertEqual(r["uncompared_prematch_fixture_count"],1)
    def test_tampered_receipt(self):
        kw,p=fixture()
        kw["live_cases"]["synthetic"]["inputs"]["prematch_receipt"]["status"]="READY"
        self.check(kw,False)

if __name__=="__main__":unittest.main()
