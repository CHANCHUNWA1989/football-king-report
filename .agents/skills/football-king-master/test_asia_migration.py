import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json
import asia_migration as a

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.remote=self.base/"remote.git"
        self.first=a.init(self.remote,a.fixture_bytes(0))
    def writer(self,name="writer"):
        return a.clone(self.remote,self.base/name)
    def test_fixture_uses_existing_validator(self):
        self.assertEqual(a.validate(a.fixture_bytes(0))["production_recommendations"],"DISABLED")
    def test_unknown_field_rejected(self):
        d=json.loads(a.fixture_bytes(0));d["secret"]="synthetic"
        with self.assertRaises(ValueError): a.validate(json.dumps(d).encode())
    def test_unsafe_flag(self):
        d=json.loads(a.fixture_bytes(0));d["production_recommendations"]="ENABLED"
        with self.assertRaises(ValueError): a.validate(json.dumps(d).encode())
    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError): a.validate(b'{"schema":1,"schema":2}')
    def test_invalid_timestamp(self):
        d=json.loads(a.fixture_bytes(0));d["collected_utc"]="2026-01-01T00:00:00"
        with self.assertRaises(ValueError): a.validate(json.dumps(d).encode())
    def test_newer_success(self):
        w=self.writer();new=a.prepare(w,self.first,a.fixture_bytes(1))
        self.assertTrue(a.push(w,self.remote,new))
        self.assertEqual(a.latest(self.remote,new)["raw"],a.fixture_bytes(1))
    def test_idempotent(self):
        self.assertEqual(a.prepare(self.writer(),self.first,a.fixture_bytes(0)),self.first)
    def test_equal_time_different_bytes(self):
        w=self.writer()
        with self.assertRaises(ValueError): a.prepare(w,self.first,a.fixture_bytes(0)+b" ")
    def test_stale(self):
        w=self.writer();new=a.prepare(w,self.first,a.fixture_bytes(2));self.assertTrue(a.push(w,self.remote,new))
        w2=self.writer("w2")
        with self.assertRaises(ValueError): a.prepare(w2,new,a.fixture_bytes(1))
    def test_concurrent_siblings(self):
        writers=[self.writer("w"+str(i)) for i in range(8)]
        commits=[a.prepare(w,self.first,a.fixture_bytes(i+1)) for i,w in enumerate(writers)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda x:a.push(x[0],self.remote,x[1]),zip(writers,commits)))
        self.assertEqual(sum(results),1)
        winner=commits[results.index(True)]
        self.assertEqual(a.latest(self.remote,winner)["generation"],2)
    def test_stale_writer_rejected(self):
        w1=self.writer("w1");w2=self.writer("w2")
        one=a.prepare(w1,self.first,a.fixture_bytes(1));two=a.prepare(w2,self.first,a.fixture_bytes(2))
        self.assertTrue(a.push(w1,self.remote,one));self.assertFalse(a.push(w2,self.remote,two))
        self.assertEqual(a.tip(self.remote),one)
    def test_untrusted_tip(self):
        with self.assertRaises(ValueError): a.latest(self.remote,"f"*40)
    def test_delete_denied(self):
        w=self.writer()
        self.assertFalse(a.delete_drill(w,self.remote))
        self.assertEqual(a.tip(self.remote),self.first)
    def test_recovery(self):
        w=self.writer();new=a.prepare(w,self.first,a.fixture_bytes(1));self.assertTrue(a.push(w,self.remote,new))
        bundle=self.base/"backup.bundle";a.backup(self.remote,new,bundle)
        restored=a.recover(bundle,self.base/"restored.git",new)
        self.assertEqual(a.latest(restored,new)["raw"],a.fixture_bytes(1))
    def test_stale_bundle(self):
        b=self.base/"backup.bundle";a.backup(self.remote,self.first,b)
        w=self.writer();new=a.prepare(w,self.first,a.fixture_bytes(1));self.assertTrue(a.push(w,self.remote,new))
        with self.assertRaises(ValueError): a.recover(b,self.base/"restored.git",new)
    def test_corrupt_bundle(self):
        b=self.base/"bad.bundle";b.write_bytes(b"invalid")
        with self.assertRaises((ValueError,RuntimeError)): a.recover(b,self.base/"restored.git",self.first)
    def test_raw_bytes_preserved(self):
        raw=a.fixture_bytes(1)+b" "
        w=self.writer();new=a.prepare(w,self.first,raw);self.assertTrue(a.push(w,self.remote,new))
        self.assertEqual(a.latest(self.remote,new)["raw"],raw)
    def test_manifest_mismatch(self):
        w=self.writer()
        with self.assertRaises(ValueError): a.prepare(w,"a"*40,a.fixture_bytes(1))
if __name__=="__main__": unittest.main(verbosity=2)
