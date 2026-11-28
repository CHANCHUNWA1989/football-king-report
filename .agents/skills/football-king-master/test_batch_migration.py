"""Synthetic multi-file migration regression cases."""
import json
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import batch_migration as b
import git_state_anchor as g

class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.remote=self.base/"remote.git"
        self.first=b.init(self.remote,b.fixture(1,0))
    def writer(self,name="writer"):
        return b.clone(self.remote,self.base/name)
    def advance(self):
        w=self.writer()
        x=b.prepare(w,self.first,b.fixture(2,20))
        self.assertTrue(b.push(w,self.remote,x))
        return x
    def test_complete_genesis(self):
        x=b.latest(self.remote,self.first)
        self.assertEqual(len(x["docs"]),6)
        self.assertEqual(len(x["tree"]),13)
    def test_atomic_complete_batch(self):
        x=self.advance()
        y=b.latest(self.remote,x)
        self.assertEqual(len(y["tree"]),19)
        self.assertEqual(y["docs"],b.fixture(2,20))
    def test_partial_batch_rejected(self):
        docs=b.fixture(2,20);docs.pop(b.STREAMS[0])
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_extra_file_rejected(self):
        docs=b.fixture(2,20);docs["evil"]=b"{}"
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_unsafe_flag(self):
        docs=b.fixture(2,20);k=b.STREAMS[0]
        docs[k]=docs[k].replace(b"DISABLED",b"ENABLED")
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_mixed_batch(self):
        docs=b.fixture(2,20);docs[b.STREAMS[0]]=b.fixture(3,20)[b.STREAMS[0]]
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_old_timestamp_single_stream(self):
        docs=b.fixture(2,20);k=b.STREAMS[0]
        docs[k]=b.fixture(2,0)[k]
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_timestamp_naive(self):
        docs=b.fixture(2,20);k=b.STREAMS[0]
        docs[k]=docs[k].replace(b"+00:00",b"")
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,docs)
    def test_history_unchanged(self):
        x=self.advance()
        old=b.latest(self.remote,self.first,require_tip=False)["tree"]
        new=b.latest(self.remote,x)["tree"]
        self.assertTrue(all(new[k]==v for k,v in old.items() if k.startswith("history-")))
    def test_duplicate_identical(self):
        self.assertEqual(b.prepare(self.writer(),self.first,b.fixture(1,0)),self.first)
    def test_batch_id_collision(self):
        with self.assertRaises(ValueError): b.prepare(self.writer(),self.first,b.fixture(1,20))
    def test_old_batch_replay(self):
        x=self.advance()
        with self.assertRaises(ValueError): b.prepare(self.writer("after"),x,b.fixture(1,0))
    def test_failure_before_publish(self):
        w=self.writer()
        with self.assertRaises(RuntimeError): b.prepare(w,self.first,b.fixture(2,20),fail_before_commit=True)
        self.assertEqual(b.tip(self.remote),self.first)
        self.assertEqual(len(b.latest(self.remote,self.first)["tree"]),13)
    def test_prepared_not_visible(self):
        w=self.writer()
        b.prepare(w,self.first,b.fixture(2,20))
        self.assertEqual(b.tip(self.remote),self.first)
    def test_lost_ack_replay(self):
        x=self.advance()
        self.assertEqual(b.prepare(self.writer("after"),x,b.fixture(2,20)),x)
    def test_sibling_concurrency(self):
        writers=[self.writer("w"+str(i)) for i in range(8)]
        commits=[b.prepare(w,self.first,b.fixture(i+2,20+i)) for i,w in enumerate(writers)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(lambda x:b.push(x[0],self.remote,x[1]),zip(writers,commits)))
        self.assertEqual(sum(result),1)
        self.assertEqual(len(b.latest(self.remote,commits[result.index(True)])["tree"]),19)
    def test_retry_revalidate(self):
        w1=self.writer("one");w2=self.writer("two")
        one=b.prepare(w1,self.first,b.fixture(2,20));two=b.prepare(w2,self.first,b.fixture(3,40))
        self.assertTrue(b.push(w1,self.remote,one));self.assertFalse(b.push(w2,self.remote,two))
        w3=self.writer("three");three=b.prepare(w3,one,b.fixture(3,40))
        self.assertTrue(b.push(w3,self.remote,three));self.assertEqual(b.latest(self.remote,three)["generation"],3)
    def test_exact_bytes(self):
        docs=b.fixture(2,20);docs[b.STREAMS[0]]+=b" "
        w=self.writer();x=b.prepare(w,self.first,docs);self.assertTrue(b.push(w,self.remote,x))
        self.assertEqual(b.latest(self.remote,x)["docs"],docs)
    def test_wrong_trusted_tip(self):
        with self.assertRaises(ValueError): b.latest(self.remote,"f"*40)
    def test_recover(self):
        x=self.advance();bundle=self.base/"copy.bundle"
        b.backup(self.remote,x,bundle)
        restored=b.recover(bundle,self.base/"restored.git",x)
        self.assertEqual(b.latest(restored,x)["docs"],b.fixture(2,20))
    def test_old_bundle(self):
        bundle=self.base/"old.bundle";b.backup(self.remote,self.first,bundle)
        x=self.advance()
        with self.assertRaises(ValueError): b.recover(bundle,self.base/"restored.git",x)
    def test_corrupt_bundle(self):
        bundle=self.base/"bad.bundle";bundle.write_bytes(b"bad")
        with self.assertRaises((ValueError,RuntimeError)): b.recover(bundle,self.base/"restored.git",self.first)
    def test_history_rewrite_rejected(self):
        w=self.writer()
        x=b.prepare(w,self.first,b.fixture(2,20))
        tree=b.read_tree(w,x);tree.pop("history-0001-"+b.STREAMS[0]+".json")
        forged=b.commit_tree(w,self.first,tree)
        with self.assertRaises(ValueError): b.push(w,self.remote,forged)
        self.assertEqual(b.tip(self.remote),self.first)
    def test_unknown_tree_entry(self):
        w=self.writer();x=b.prepare(w,self.first,b.fixture(2,20))
        tree=b.read_tree(w,x);tree["unknown.json"]=tree["manifest.json"]
        forged=b.commit_tree(w,self.first,tree)
        with self.assertRaises(ValueError): b.push(w,self.remote,forged)
    def test_delete_denied(self):
        self.assertFalse(b.delete_drill(self.writer(),self.remote))
        self.assertEqual(b.tip(self.remote),self.first)
if __name__=="__main__": unittest.main(verbosity=2)
