import copy
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import git_state_anchor as a
import deployment_checkpoint as c
import research_scheduler as s

def raw(slots=(0,),stopped=False):
    return c.canonical(dict(schema=c.SCHEMA,release="HOLD",production_recommendations="DISABLED",stopped=stopped,jobs=[],cycles=[dict(slot=i,status="SUCCEEDED",summary={}) for i in slots]))
class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)
        self.store=self.p/"store.git"
        a.init(self.store)
        self.first=a.publish(self.store,raw(),None)
    def test_exact_tip(self):
        self.assertEqual(a.latest(self.store,self.first)["raw"],raw())
    def test_no_untrusted_tip(self):
        with self.assertRaises(ValueError): a.latest(self.store,None)
    def test_wrong_tip(self):
        with self.assertRaises(ValueError): a.latest(self.store,"f"*40)
    def test_successor(self):
        second=a.publish(self.store,raw((0,21600)),self.first)
        self.assertEqual(a.latest(self.store,second)["generation"],2)
    def test_stale_tip_rejected(self):
        a.publish(self.store,raw((0,21600)),self.first)
        with self.assertRaises(ValueError): a.latest(self.store,self.first)
    def test_stale_writer_rejected(self):
        a.publish(self.store,raw((0,21600)),self.first)
        with self.assertRaises(ValueError): a.publish(self.store,raw((0,43200)),self.first)
    def test_duplicate_not_new(self):
        with self.assertRaises(ValueError): a.publish(self.store,raw(),self.first)
    def test_rollback(self):
        second=a.publish(self.store,raw((0,21600)),self.first)
        with self.assertRaises(ValueError): a.publish(self.store,raw(),second)
    def test_concurrent_CAS(self):
        def attempt(i):
            try: return a.publish(self.store,raw((0,21600*(i+1))),self.first)
            except (ValueError,RuntimeError): return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(attempt,range(16)))
        wins=[x for x in results if x is not None]
        self.assertEqual(len(wins),1)
        self.assertEqual(a.latest(self.store,wins[0])["generation"],2)
    def test_bundle_recover(self):
        second=a.publish(self.store,raw((0,21600)),self.first)
        bundle=self.p/"copy.bundle"
        a.backup(self.store,second,bundle)
        restored=self.p/"recovered.git"
        a.recover(bundle,restored,second)
        self.assertEqual(a.latest(restored,second)["raw"],raw((0,21600)))
        state=self.p/"state"
        c.restore(state,a.latest(restored,second)["raw"],a.latest(restored,second)["checkpointSha256"])
        self.assertIsNone(s.claim(state,21600))
    def test_old_bundle_rejected(self):
        bundle=self.p/"old.bundle";a.backup(self.store,self.first,bundle)
        second=a.publish(self.store,raw((0,21600)),self.first)
        with self.assertRaises(ValueError): a.recover(bundle,self.p/"recovered.git",second)
    def test_corrupt_bundle(self):
        bundle=self.p/"bad.bundle";bundle.write_bytes(b"bad")
        with self.assertRaises((ValueError,RuntimeError)): a.recover(bundle,self.p/"recovered.git",self.first)
    def test_no_overwrite(self):
        bundle=self.p/"copy.bundle";a.backup(self.store,self.first,bundle)
        with self.assertRaises((ValueError,FileExistsError)): a.backup(self.store,self.first,bundle)
    def test_stopped_cannot_extend(self):
        x=a.publish(self.store,raw((0,21600),True),self.first)
        with self.assertRaises(ValueError): a.publish(self.store,raw((0,21600,43200)),x)
    def test_ref_rollback(self):
        second=a.publish(self.store,raw((0,21600)),self.first)
        a.git(self.store,["update-ref",a.REF,self.first,second])
        with self.assertRaises(ValueError): a.latest(self.store,second)
    def test_nonempty_genesis_rejected(self):
        with self.assertRaises(ValueError): a.publish(self.store,raw(),None)
    def test_unsafe_path(self):
        with self.assertRaises((ValueError,FileExistsError)): a.init(self.store)
class ReviewTests(unittest.TestCase):
    def setUp(self): self.head="a"*40
    def review(self,login="other",state="APPROVED",head=None,id=1,assoc="COLLABORATOR"):
        return dict(id=id,user=dict(login=login),state=state,commit_id=head or self.head,author_association=assoc)
    def test_empty(self):
        self.assertEqual(a.review_gate(self.head,"author",[])["candidateApprovals"],0)
    def test_self_approval(self):
        self.assertEqual(a.review_gate(self.head,"author",[self.review("AUTHOR")])["candidateApprovals"],0)
    def test_stale(self):
        self.assertEqual(a.review_gate(self.head,"author",[self.review(head="b"*40)])["candidateApprovals"],0)
    def test_candidate_not_agent(self):
        r=a.review_gate(self.head,"author",[self.review()])
        self.assertEqual(r["candidateApprovals"],1)
        self.assertEqual(r["independentAgentReviews"],0)
        self.assertFalse(r["deploymentAuthorized"])
    def test_dismissal(self):
        self.assertEqual(a.review_gate(self.head,"author",[self.review(),self.review(state="DISMISSED",id=2)])["candidateApprovals"],0)
    def test_changes_requested(self):
        r=a.review_gate(self.head,"author",[self.review(),self.review(state="CHANGES_REQUESTED",id=2)])
        self.assertEqual(r["blockingReviews"],1)
        self.assertEqual(r["candidateApprovals"],0)
    def test_untrusted_association(self):
        self.assertEqual(a.review_gate(self.head,"author",[self.review(assoc="NONE")])["candidateApprovals"],0)
    def test_comment_not_approval(self):
        self.assertEqual(a.review_gate(self.head,"author",[self.review(state="COMMENTED")])["candidateApprovals"],0)
if __name__=="__main__": unittest.main(verbosity=2)
