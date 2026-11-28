import tempfile
import unittest
from pathlib import Path
import json
import hashlib
import research_scheduler as s
import research_queue as q
import deployment_checkpoint as c

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.state=self.base/"state"
        self.dest=self.base/"restored"
        s.init(self.state)
    def complete(self, outcome="SUCCEEDED"):
        token=s.claim(self.state,0)
        s.finish(self.state,0,token,outcome,{})
    def checkpoint(self):
        return c.export_bytes(self.state)
    def restore(self,raw):
        return c.restore(self.dest,raw,hashlib.sha256(raw).hexdigest())
    def test_roundtrip(self):
        self.complete()
        self.restore(self.checkpoint())
        self.assertEqual(s.status(self.state),s.status(self.dest))
    def test_no_duplicate_after_restore(self):
        self.complete()
        self.restore(self.checkpoint())
        self.assertIsNone(s.claim(self.dest,0))
        self.assertIsNotNone(s.claim(self.dest,21600))
    def test_stopped_preserved(self):
        self.complete(); q.stop(self.state)
        self.restore(self.checkpoint())
        self.assertTrue(s.status(self.dest)["stopped"])
        self.assertIsNone(s.claim(self.dest,21600))
    def test_blocked_preserved(self):
        self.complete("BLOCKED")
        self.restore(self.checkpoint())
        self.assertIsNone(s.claim(self.dest,21600))
    def test_running_refused(self):
        s.claim(self.state,0)
        with self.assertRaises(ValueError): self.checkpoint()
    def test_running_job_refused(self):
        q.enqueue(self.state,"a"*64,now=0)
        q.claim(self.state,"a"*64,now=0)
        with self.assertRaises(ValueError): self.checkpoint()
    def test_job_state_preserved(self):
        key="a"*64
        q.enqueue(self.state,key,now=0)
        token=q.claim(self.state,key,now=0)
        q.finish(self.state,key,token,"TRANSIENT",now=1)
        self.restore(self.checkpoint())
        self.assertEqual(q.snapshot(self.state),q.snapshot(self.dest))
    def test_tamper_rejected(self):
        raw=self.checkpoint()
        with self.assertRaises(ValueError): c.restore(self.dest,raw+b" ",hashlib.sha256(raw).hexdigest())
        self.assertFalse(self.dest.exists())
    def test_wrong_digest(self):
        with self.assertRaises(ValueError): c.restore(self.dest,self.checkpoint(),"0"*64)
    def test_overwrite_refused(self):
        raw=self.checkpoint(); self.restore(raw)
        with self.assertRaises(FileExistsError): self.restore(raw)
    def test_schema_spoof(self):
        d=json.loads(self.checkpoint()); d["release"]="READY"
        with self.assertRaises(ValueError): self.restore(json.dumps(d).encode())
    def test_duplicate_slot(self):
        self.complete();d=json.loads(self.checkpoint());d["cycles"].append(d["cycles"][0])
        with self.assertRaises(ValueError): self.restore(json.dumps(d).encode())
    def test_running_injected(self):
        self.complete();d=json.loads(self.checkpoint());d["cycles"][0]["status"]="RUNNING"
        with self.assertRaises(ValueError): self.restore(json.dumps(d).encode())
    def test_alert_on_stop(self):
        q.stop(self.state)
        self.assertEqual(c.health(self.state)["level"],"BLOCKED")
    def test_alert_on_blocked(self):
        self.complete("BLOCKED")
        self.assertEqual(c.health(self.state)["level"],"BLOCKED")
    def test_healthy_still_review_blocked(self):
        self.complete()
        h=c.health(self.state)
        self.assertEqual(h["level"],"RESEARCH_ONLY")
        self.assertFalse(h["deploymentAuthorized"])
    def test_empty_alert(self):
        self.assertEqual(c.health(self.state)["level"],"NO_CYCLE")
    def test_stale_cycle(self):
        self.complete()
        self.assertEqual(c.health(self.state,43200)["level"],"STALE")
    def test_noncanonical_valid_data(self):
        d=json.loads(self.checkpoint())
        with self.assertRaises(ValueError): self.restore(json.dumps(d).encode())
    def test_retry_cycle_preserved(self):
        self.complete("RETRY_WAIT")
        self.restore(self.checkpoint())
        self.assertEqual(c.health(self.dest)["level"],"RETRY_WAIT")
        self.assertIsNone(s.claim(self.dest,0))
        self.assertIsNotNone(s.claim(self.dest,21600))
if __name__=="__main__": unittest.main(verbosity=2)
