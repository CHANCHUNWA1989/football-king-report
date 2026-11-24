"""Adversarial P0 approval/cadence regressions, no real external authorizations."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from ops.archive_independent_review_gate import assess, ARCHIVE, REPO_ID, OWNER_ID, TARGETS, verify_linked
from ops.german_cadence_window import evaluate, WORKFLOW


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.head="a"*40
        self.now=datetime(2026,11,24,13,tzinfo=timezone.utc)
        self.pr=dict(number=571,head=dict(sha=self.head,ref=TARGETS[571],repo=dict(id=REPO_ID)),
                     base=dict(sha=ARCHIVE,ref="research/forward-provenance-archive",repo=dict(id=REPO_ID)),
                     state="open",merged=False,user=dict(id=OWNER_ID))
        self.r=dict(id=1,user=dict(id=7,type="User"),state="APPROVED",commit_id=self.head,
                    submitted_at="2026-11-24T12:00:00Z",author_association="COLLABORATOR")

    def check(self,rows,ids=frozenset({7})):
        return assess(self.pr,rows,self.head,self.now,reviewer_ids=ids)

    def test_unprovisioned_policy_and_wrong_commit_never_count(self):
        self.assertFalse(self.check([self.r],frozenset())["exact_head_independent_review_observed"])
        self.assertFalse(self.check([dict(self.r,commit_id="b"*40)])["exact_head_independent_review_observed"])

    def test_self_review_bot_and_outsider_rejected(self):
        for u in [dict(id=OWNER_ID,type="User"),dict(id=7,type="Bot")]:
            self.assertFalse(self.check([dict(self.r,user=u)],frozenset({OWNER_ID,7}))["exact_head_independent_review_observed"])
        self.assertFalse(self.check([dict(self.r,author_association="NONE")])["exact_head_independent_review_observed"])

    def test_later_dismissal_and_dissent_block(self):
        self.assertTrue(self.check([self.r])["exact_head_independent_review_observed"])
        for state in ["DISMISSED","CHANGES_REQUESTED"]:
            self.assertFalse(self.check([self.r,dict(self.r,id=2,state=state,submitted_at="2026-11-24T12:30:00Z")])["exact_head_independent_review_observed"])

    def test_duplicate_and_wrong_head_fail_closed(self):
        with self.assertRaises(ValueError): self.check([self.r,self.r])
        self.pr["head"]["sha"]="b"*40
        with self.assertRaises(ValueError): self.check([self.r])

    def test_wrong_linked_bytes_rejected(self):
        with self.assertRaises(ValueError): verify_linked(b"{}")


class CadenceTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,24,13,tzinfo=timezone.utc)
        self.rows=[]
        for i in range(6):
            t=self.now-timedelta(hours=i+0.25)
            self.rows.append(dict(id=100-i,repository={"id":REPO_ID},head_repository={"id":REPO_ID},
                                  path=WORKFLOW,head_branch="main",event="schedule",run_attempt=1,
                                  status="completed",conclusion="success",created_at=t.isoformat(),updated_at=(t+timedelta(minutes=1)).isoformat()))

    def test_duplicate_or_manual_run_rejected(self):
        for rows in [self.rows+[self.rows[0]],[dict(self.rows[0],event="workflow_dispatch")]]:
            with self.assertRaises(ValueError): evaluate(".", "a"*40,rows,self.now)

    @patch("ops.german_cadence_window.inspect",return_value={"status":"HOLD_FRESH_RESEARCH_PUBLICATION_CORRELATED","publication_correlated":True})
    @patch("ops.german_cadence_window._git",side_effect=__import__("ops.history_blob_retention_preflight",fromlist=["RetentionHold"]).RetentionHold("MISSING"))
    def test_successful_run_metadata_alone_not_enough(self,git,inspect):
        r=evaluate(".", "a"*40,self.rows,self.now)
        self.assertFalse(r["research_cadence_window_passed"])
        self.assertEqual(r["archived_publications_verified"],0)
        self.assertFalse(r["fallback_allowed"])


if __name__=="__main__":
    unittest.main()
