"""V2.4 negative evidence-binding and identity contract tests."""
import copy
import unittest
import cross_review as q

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.binding={"checkoutSha":"a"*40,"files":{"evidence/settled.json":"b"*64}}
        self.reports=[dict(**q.FLAGS,role=r,kind="DETERMINISTIC_WORKER",status="PASS",
                           binding=copy.deepcopy(self.binding),details={"scope":"TEST"}) for r in q.ROLES]
    def run_review(self):
        return q.aggregate(self.binding,self.reports)
    def test_four_workers_not_agents(self):
        r=self.run_review()
        self.assertEqual(r["checkedRoles"],4)
        self.assertEqual(r["independentAgentReviews"],0)
        self.assertFalse(r["mergeAuthorized"])
    def test_missing_role(self):
        self.reports.pop()
        with self.assertRaises(ValueError): self.run_review()
    def test_duplicate_role(self):
        self.reports[1]["role"]="code"
        with self.assertRaises(ValueError): self.run_review()
    def test_unknown_role(self):
        self.reports[1]["role"]="other"
        with self.assertRaises(ValueError): self.run_review()
    def test_stale_commit(self):
        self.reports[1]["binding"]["checkoutSha"]="c"*40
        with self.assertRaises(ValueError): self.run_review()
    def test_changed_hash(self):
        self.reports[1]["binding"]["files"]["evidence/settled.json"]="c"*64
        with self.assertRaises(ValueError): self.run_review()
    def test_failed_worker(self):
        self.reports[1]["status"]="FAIL"
        with self.assertRaises(ValueError): self.run_review()
    def test_spoofed_agent(self):
        self.reports[1]["kind"]="INDEPENDENT_AGENT"
        with self.assertRaises(ValueError): self.run_review()
    def test_spoofed_review_count(self):
        self.reports[1]["independentAgentReviews"]=1
        with self.assertRaises(ValueError): self.run_review()
    def test_bool_int_not_equivalent(self):
        self.reports[1]["independentAgentReviews"]=False
        with self.assertRaises(ValueError): self.run_review()
    def test_merge_flag(self):
        self.reports[1]["mergeAuthorized"]=True
        with self.assertRaises(ValueError): self.run_review()
    def test_unsafe_release(self):
        self.reports[1]["release"]="READY"
        with self.assertRaises(ValueError): self.run_review()
    def test_missing_details(self):
        del self.reports[1]["details"]
        with self.assertRaises(ValueError): self.run_review()
    def test_bool_probability(self):
        self.assertFalse(q.probs([True,0,0]))
    def test_normalization(self):
        self.assertAlmostEqual(sum(q.temperature([.8,.1,.1],1.5)),1)
    def test_known_log_loss_and_brier(self):
        self.assertAlmostEqual(q.loss([.5,.3,.2],0),.6931471805599453)
        self.assertAlmostEqual(q.brier([.5,.3,.2],0),.38)
    def test_time_without_zone(self):
        with self.assertRaises(ValueError): q.utc("2026-11-01T10:00:00")
    def test_empty_model_replay(self):
        f,p,m=q.recalc(dict(schema="football-king-forward-research-1",production_recommendations="DISABLED",n=0,samples=[]))
        self.assertEqual((f,p,m),([],[],{}))
if __name__=="__main__": unittest.main(verbosity=2)
