"""Research queue tests: isolated real SQLite state, not live source data."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
import research_queue as q

KEY = "a" * 64
OTHER = "b" * 64

class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name) / "state"
        q.init(self.dir)
    def put(self, key=KEY):
        return q.enqueue(self.dir, key, now=100)
    def row(self):
        return q.snapshot(self.dir)["jobs"][0]
    def claim(self, now=100):
        return q.claim(self.dir, KEY, now=now)
    def test_persist_across_connections(self):
        self.put()
        self.assertEqual(self.row()["status"], "PENDING")
        self.assertEqual(q.snapshot(self.dir)["jobs"][0]["id"], KEY)
    def test_duplicate_enqueue(self):
        self.assertTrue(self.put())
        self.assertFalse(self.put())
        self.assertEqual(len(q.snapshot(self.dir)["jobs"]), 1)
    def test_concurrent_enqueue(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.put(), range(32)))
        self.assertEqual(sum(results), 1)
    def test_concurrent_claim(self):
        self.put()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.claim(), range(16)))
        self.assertEqual(sum(x is not None for x in results), 1)
        self.assertEqual(self.row()["attempts"], 1)
    def test_success_is_terminal(self):
        self.put(); token = self.claim()
        q.finish(self.dir, KEY, token, "SUCCESS", now=101)
        self.assertEqual(self.row()["status"], "SUCCEEDED")
        self.assertIsNone(self.claim(200))
        self.assertFalse(self.put())
    def test_retry_delay(self):
        self.put(); token = self.claim()
        q.finish(self.dir, KEY, token, "TRANSIENT", now=101)
        self.assertEqual(self.row()["status"], "RETRY_WAIT")
        self.assertIsNone(self.claim(102))
        self.assertIsNotNone(self.claim(103))
    def test_retry_cap(self):
        self.put()
        for now in (100, 103, 108):
            token = self.claim(now)
            self.assertIsNotNone(token)
            q.finish(self.dir, KEY, token, "TRANSIENT", now=now+1)
        self.assertEqual(self.row()["attempts"], 3)
        self.assertEqual(self.row()["status"], "BLOCKED")
        self.assertIsNone(self.claim(999))
    def test_permanent_failure_no_retry(self):
        self.put(); q.finish(self.dir, KEY, self.claim(), "PERMANENT", now=101)
        self.assertEqual(self.row()["status"], "BLOCKED")
        self.assertIsNone(self.claim(200))
    def test_stop_persists(self):
        self.put(); q.stop(self.dir)
        self.assertTrue(q.snapshot(self.dir)["stopped"])
        self.assertIsNone(self.claim())
        self.assertFalse(self.put(OTHER))
    def test_stop_during_run_prevents_retry(self):
        self.put(); token = self.claim(); q.stop(self.dir)
        q.finish(self.dir, KEY, token, "TRANSIENT", now=101)
        self.assertEqual(self.row()["status"], "BLOCKED")
        self.assertIsNone(self.claim(200))
    def test_wrong_token_cannot_finish(self):
        self.put(); token = self.claim()
        with self.assertRaises(ValueError):
            q.finish(self.dir, KEY, "wrong", "SUCCESS", now=101)
        self.assertEqual(self.row()["status"], "RUNNING")
        q.finish(self.dir, KEY, token, "SUCCESS", now=101)
    def test_interrupted_running_blocks_new_claim(self):
        self.put(); self.claim(); self.put(OTHER)
        self.assertIsNone(q.claim(self.dir, OTHER, now=999))
        self.assertEqual(self.row()["status"], "RUNNING")
    def test_changed_input_blocks_old_task(self):
        self.put()
        self.assertIsNone(q.claim(self.dir, OTHER, now=100))
        self.assertEqual(self.row()["status"], "PENDING")
    def test_bad_key_rejected(self):
        with self.assertRaises(ValueError):
            q.enqueue(self.dir, "../unsafe", now=100)
    def test_reinit_rejected(self):
        with self.assertRaises(FileExistsError):
            q.init(self.dir)
    def test_flags_invariant(self):
        self.put(); result=q.snapshot(self.dir)
        self.assertEqual(result["release"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["canPromote"])
    def test_bad_hub_output(self):
        self.assertEqual(q.classify(0, b"not json"), "PERMANENT")
        self.assertEqual(q.classify(1, b"{}"), "PERMANENT")
        self.assertEqual(q.classify(0, b'{"status":"RESEARCH_COMPLETE"}'), "PERMANENT")
    def test_valid_hub_output(self):
        result = dict(status="RESEARCH_COMPLETE",completed=8,checksPassed=124,
                      release="HOLD",production_recommendations="DISABLED",
                      canPromote=False,mergeAuthorized=False,automaticProductionRepair=False,
                      inputsUnchanged=True,diagnosticHashesMatch=True)
        self.assertEqual(q.classify(0, json.dumps(result).encode()), "SUCCESS")
        result["canPromote"]=True
        self.assertEqual(q.classify(0, json.dumps(result).encode()), "PERMANENT")
    def test_actual_process_restart_and_stop(self):
        cli = pathlib.Path(q.__file__)
        def call(*args):
            p=subprocess.run([sys.executable,str(cli),*args,str(self.dir)],capture_output=True,check=True)
            return json.loads(p.stdout)
        self.put()
        self.assertEqual(call("status")["jobs"][0]["id"],KEY)
        call("stop")
        self.assertTrue(call("status")["stopped"])
    def test_sqlite_integrity(self):
        import sqlite3
        self.put()
        with sqlite3.connect(self.dir/"queue.sqlite3") as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
    def test_database_symlink_rejected(self):
        other=pathlib.Path(self.tmp.name)/"elsewhere"
        (self.dir/"queue.sqlite3").rename(other)
        (self.dir/"queue.sqlite3").symlink_to(other)
        with self.assertRaises(ValueError):
            q.snapshot(self.dir)

if __name__ == "__main__":
    unittest.main(verbosity=2)
