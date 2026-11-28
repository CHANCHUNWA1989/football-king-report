import tempfile
import unittest
from pathlib import Path
import copy
import core_migration as c
import git_state_anchor as g
import asia_migration as a

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.remote=self.base/"remote.git"
        self.first=c.init(self.remote)
    def writer(self,name="writer"):
        return a.clone(self.remote,self.base/name)
    def advance(self):
        w=self.writer();x=c.prepare(w,self.first,c.fixture(2));self.assertTrue(c.push(w,self.remote,x));return x
    def test_genesis(self):
        x=c.latest(self.remote,self.first)
        self.assertEqual(len(x["files"]),17)
        self.assertEqual(x["ledger"]["n"],1)
    def test_atomic_append(self):
        x=c.latest(self.remote,self.advance())
        self.assertEqual(len(x["files"]),32)
        self.assertEqual(x["ledger"]["n"],2)
    def test_historical_bytes(self):
        old=c.latest(self.remote,self.first)
        new=c.latest(self.remote,self.advance())
        self.assertTrue(all(new["files"][k]==v for k,v in old["files"].items() if k.startswith("batch-")))
        self.assertEqual(new["ledger"]["samples"][0],old["ledger"]["samples"][0])
    def test_missing_proof(self):
        f=c.fixture(2);f["proof"].pop("shadow.json")
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_tampered_proof(self):
        f=c.fixture(2);f["proof"]["paired.json"]=b'{}'
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_model_b_changed(self):
        f=c.fixture(2);f["ledger"]["samples"][0]["ab"]=[.99,.005,.005]
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_model_c_changed(self):
        f=c.fixture(2);f["ledger"]["samples"][0]["c"]=[.99,.005,.005]
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_leakage(self):
        f=c.fixture(2);f["ledger"]["samples"][0]["forecast_utc"]=f["ledger"]["samples"][0]["kickoff_utc"]
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_early_settlement(self):
        f=c.fixture(2);f["ledger"]["checked_utc"]=f["ledger"]["samples"][0]["forecast_utc"]
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_conflicting_result(self):
        f=c.fixture(1);f["ledger"]["samples"][0]["y"]=2
        with self.assertRaises(ValueError): c.prepare(self.writer(),self.first,f)
    def test_idempotent(self):
        self.assertEqual(c.prepare(self.writer(),self.first,c.fixture(1)),self.first)
    def test_failure_no_publish(self):
        with self.assertRaises(RuntimeError): c.prepare(self.writer(),self.first,c.fixture(2),fail=True)
        self.assertEqual(g.tip(self.remote),self.first)
    def test_prepared_invisible(self):
        c.prepare(self.writer(),self.first,c.fixture(2))
        self.assertEqual(g.tip(self.remote),self.first)
    def test_concurrent_merge_retry(self):
        one=self.writer("one");two=self.writer("two")
        x=c.prepare(one,self.first,c.fixture(2));y=c.prepare(two,self.first,c.fixture(3))
        self.assertTrue(c.push(one,self.remote,x));self.assertFalse(c.push(two,self.remote,y))
        three=self.writer("three");z=c.prepare(three,x,c.fixture(3))
        self.assertTrue(c.push(three,self.remote,z))
        self.assertEqual(c.latest(self.remote,z)["ledger"]["n"],3)
    def test_forged_history(self):
        w=self.writer();x=c.prepare(w,self.first,c.fixture(2))
        tree=c.b.read_tree(w,x);tree.pop(next(k for k in tree if k.startswith("batch-0001-")))
        forged=c.b.commit_tree(w,self.first,tree)
        with self.assertRaises(ValueError): c.push(w,self.remote,forged)
    def test_exact_tip_restore(self):
        x=self.advance();p=self.base/"copy.bundle"
        c.backup(self.remote,x,p);r=c.recover(p,self.base/"restored.git",x)
        self.assertEqual(c.latest(r,x)["files"],c.latest(self.remote,x)["files"])
    def test_stale_bundle(self):
        p=self.base/"copy.bundle";c.backup(self.remote,self.first,p);x=self.advance()
        with self.assertRaises(ValueError): c.recover(p,self.base/"restored.git",x)
    def test_gate_never_authorizes(self):
        out=c.qualification()
        self.assertFalse(out["deploymentAuthorized"]);self.assertFalse(out["signatureAuthenticated"])
        self.assertFalse(out["continuousOperationVerified"]);self.assertEqual(out["release"],"HOLD")
if __name__=="__main__": unittest.main(verbosity=2)
