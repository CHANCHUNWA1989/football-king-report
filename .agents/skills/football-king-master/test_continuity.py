import copy
import tempfile
import unittest
from pathlib import Path
import continuity as v
import deployment_checkpoint as c
import research_scheduler as s

def doc(slots=(0,),stopped=False):
    return dict(schema=c.SCHEMA,release="HOLD",production_recommendations="DISABLED",stopped=stopped,jobs=[],cycles=[dict(slot=x,status="SUCCEEDED",summary={}) for x in slots])
def raw(d): return c.canonical(d)
class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.d=doc()
        self.raw=raw(self.d)
        self.a=v.anchor(self.raw,1,2,"a"*40)
        self.o=dict(repository=v.REPO,runId=1,artifactId=2,headSha="a"*40,conclusion="success",expired=False)
    def test_valid_anchor(self):
        self.assertEqual(v.verify(self.raw,self.a,self.o),self.d)
    def test_expired(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"expired":True})
    def test_failed_run(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"conclusion":"failure"})
    def test_wrong_artifact(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"artifactId":3})
    def test_wrong_run(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"runId":3})
    def test_wrong_head(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"headSha":"b"*40})
    def test_wrong_repo(self):
        with self.assertRaises(ValueError): v.verify(self.raw,self.a,{**self.o,"repository":"other/repo"})
    def test_wrong_digest(self):
        with self.assertRaises(ValueError): v.verify(self.raw,{**self.a,"checkpointSha256":"0"*64},self.o)
    def test_older_version(self):
        newer=v.anchor(raw(doc((0,21600))),1,2,"a"*40)
        with self.assertRaises(ValueError): v.verify(self.raw,newer,self.o)
    def test_version_field_spoof(self):
        with self.assertRaises(ValueError): v.verify(self.raw,{**self.a,"lastSlot":21600},self.o)
    def test_valid_extension(self):
        self.assertEqual(v.successor(self.raw,raw(doc((0,21600))))["addedCycles"],1)
    def test_identical_not_extension(self):
        with self.assertRaises(ValueError): v.successor(self.raw,self.raw)
    def test_truncate(self):
        with self.assertRaises(ValueError): v.successor(raw(doc((0,21600))),self.raw)
    def test_rewrite(self):
        d=doc((0,21600)); d["cycles"][0]["summary"]={"rewritten":True}
        with self.assertRaises(ValueError): v.successor(self.raw,raw(d))
    def test_stop_no_extension(self):
        with self.assertRaises(ValueError): v.successor(raw(doc(stopped=True)),raw(doc((0,21600))))
    def test_blocked_no_extension(self):
        d=doc();d["cycles"][0]["status"]="BLOCKED"
        with self.assertRaises(ValueError): v.successor(raw(d),raw(doc((0,21600))))
    def test_job_removed(self):
        d=doc();d["jobs"]=[dict(id="a"*64,status="SUCCEEDED",attempts=1,due=0,outcome="SUCCESS")]
        with self.assertRaises(ValueError): v.successor(raw(d),raw(doc((0,21600))))
    def test_terminal_job_rewrite(self):
        a=doc();a["jobs"]=[dict(id="a"*64,status="SUCCEEDED",attempts=1,due=0,outcome="SUCCESS")]
        b=copy.deepcopy(a);b["cycles"].append(doc((21600,))["cycles"][0]);b["jobs"][0]["attempts"]=2
        with self.assertRaises(ValueError): v.successor(raw(a),raw(b))
    def test_attempt_rollback(self):
        a=doc();a["jobs"]=[dict(id="a"*64,status="RETRY_WAIT",attempts=2,due=2,outcome="TRANSIENT")]
        b=copy.deepcopy(a);b["cycles"].append(doc((21600,))["cycles"][0]);b["jobs"][0]["attempts"]=1
        with self.assertRaises(ValueError): v.successor(raw(a),raw(b))
    def test_grace(self):
        self.assertEqual(v.monitor(self.d,21600+v.GRACE-1)["missedSlots"],0)
        self.assertEqual(v.monitor(self.d,21600+v.GRACE)["missedSlots"],1)
    def test_gap(self):
        self.assertEqual(v.monitor(doc((0,43200)),43200+v.GRACE)["missedSlots"],1)
    def test_empty(self):
        self.assertEqual(v.monitor(doc(()),0)["level"],"NO_CYCLE")
    def test_future(self):
        with self.assertRaises(ValueError): v.monitor(doc((21600,)),0)
    def test_stopped(self):
        self.assertEqual(v.monitor(doc(stopped=True),21600+v.GRACE)["level"],"BLOCKED")
    def test_retry_not_success(self):
        d=doc();d["cycles"][0]["status"]="RETRY_WAIT"
        self.assertEqual(v.monitor(d,v.GRACE)["missedSlots"],1)
    def test_flags(self):
        o=v.monitor(self.d,0)
        self.assertFalse(o["deploymentAuthorized"])
        self.assertFalse(o["notificationDelivered"])
        self.assertEqual(o["production_recommendations"],"DISABLED")
    def test_real_restore(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state"
            v.verify(self.raw,self.a,self.o); c.restore(p,self.raw,self.a["checkpointSha256"])
            self.assertIsNone(s.claim(p,0))
if __name__=="__main__": unittest.main(verbosity=2)
