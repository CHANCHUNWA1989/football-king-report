import unittest
import deployment_gate as d
import remote_anchor as a

class GateTests(unittest.TestCase):
    def setUp(self):
        self.head="a"*40
        self.pr={"number":788,"draft":True,"state":"open","user":{"login":"owner"},"head":{"sha":self.head,"repo":{"full_name":d.REPO}},"base":{"ref":"main","repo":{"full_name":d.REPO}},"requested_reviewers":[]}
        self.main={"name":"main","protected":True,"commit":{"sha":"b"*40}}
        self.anchor={"name":a.BRANCH,"protected":False,"commit":{"sha":a.TIP}}
        self.rules=[{"type":"non_fast_forward"},{"type":"deletion"},{"type":"pull_request"}]
        self.ci=[{"name":name,"head_sha":self.head,"status":"completed","conclusion":"success","event":"pull_request","repository":{"full_name":d.REPO},"id":i+1} for i,name in enumerate(d.REQUIRED)]
    def run_gate(self,**kw):
        x=dict(head=self.head,pr=self.pr,main=self.main,anchor=self.anchor,main_rules=self.rules,anchor_rules=[],reviews=[],collaborators=None,runs=self.ci)
        x.update(kw);return d.assess(**x)
    def test_all_ci_not_deployment(self):
        o=self.run_gate()
        self.assertEqual(o["ciPassed"],5);self.assertFalse(o["deploymentAuthorized"])
    def test_missing_ci(self): self.assertEqual(self.run_gate(runs=self.ci[:-1])["ciPassed"],4)
    def test_stale_ci(self):
        x=[dict(r,head_sha="c"*40) for r in self.ci]
        self.assertEqual(self.run_gate(runs=x)["ciPassed"],0)
    def test_duplicate_ci(self):
        self.assertEqual(self.run_gate(runs=self.ci+[dict(self.ci[0],id=99)])["ciPassed"],4)
    def test_failed_ci(self):
        x=[dict(r,conclusion="failure") if i==0 else r for i,r in enumerate(self.ci)]
        self.assertEqual(self.run_gate(runs=x)["ciPassed"],4)
    def test_fork_ci(self):
        x=[dict(r,repository={"full_name":"other/repo"}) for r in self.ci]
        self.assertEqual(self.run_gate(runs=x)["ciPassed"],0)
    def test_pr_head_mismatch(self):
        with self.assertRaises(ValueError): self.run_gate(head="c"*40)
    def test_anchor_mismatch(self):
        with self.assertRaises(ValueError): self.run_gate(anchor=dict(self.anchor,commit={"sha":"c"*40}))
    def test_no_protection(self): self.assertIn("ANCHOR_UNPROTECTED_OR_UNKNOWN",self.run_gate()["blockers"])
    def test_protection_unknown(self): self.assertIn("MAIN_UNPROTECTED_OR_UNKNOWN",self.run_gate(main=dict(self.main,protected=None))["blockers"])
    def test_rules_unknown(self): self.assertIn("MAIN_RULES_UNKNOWN_OR_INCOMPLETE",self.run_gate(main_rules=None)["blockers"])
    def test_no_independent_agent(self): self.assertIn("INDEPENDENT_REVIEW_UNVERIFIED",self.run_gate()["blockers"])
    def test_candidate_not_independent(self):
        r={"id":1,"user":{"login":"reviewer"},"state":"APPROVED","commit_id":self.head,"author_association":"COLLABORATOR"}
        o=self.run_gate(reviews=[r]);self.assertEqual(o["candidateApprovals"],1);self.assertEqual(o["independentAgentReviews"],0)
    def test_collaborator_unknown(self): self.assertIsNone(self.run_gate()["eligibleCollaboratorCandidates"])
    def test_collaborator_owner_excluded(self):
        o=self.run_gate(collaborators=[{"login":"owner","permissions":{"push":True}},{"login":"other","permissions":{"push":True}},{"login":"reader","permissions":{"push":False}}])
        self.assertEqual(o["eligibleCollaboratorCandidates"],1)
    def test_synthetic_not_production(self): self.assertIn("PRODUCTION_ANCHOR_UNAUTHENTICATED",self.run_gate()["blockers"])
    def test_safety_flags(self):
        o=self.run_gate();self.assertEqual(o["release"],"HOLD");self.assertEqual(o["production_recommendations"],"DISABLED");self.assertFalse(o["mergeAuthorized"])
if __name__=="__main__": unittest.main(verbosity=2)
