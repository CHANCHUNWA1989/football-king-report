import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ops.research_private_runtime_v52 import collect,review
from ops.research_prospective_fusion_v38 import sha
from ops.tests.test_research_private_settlement_v49 import inputs
from ops.tests.test_research_archive_score_recovery_v14 import encode

class RuntimeV52Tests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.repo=root/"repo";self.repo.mkdir()
        self.store=root/"runs";self.store.mkdir(mode=0o700)
        self.results=root/"results";self.results.mkdir(mode=0o700)
        raw,p,s,now=inputs()
        self.run_id=self.put(self.store,raw)
        self.p=self.put(self.results,encode(p))
        self.s=self.put(self.results,encode(s))
        self.kw=dict(repository=self.repo,store=self.store,result_store=self.results,
                     run_shas=[self.run_id],primary_shas=[self.p],secondary_shas=[self.s],
                     as_of=now,authorized=True)
        env=patch.dict(os.environ,{"GITHUB_ACTIONS":"false","PROPLINE_API_KEY":""})
        env.start();self.addCleanup(env.stop)
    def put(self,directory,raw):
        d=sha(raw);p=directory/(d+".json");p.write_bytes(raw);p.chmod(0o600)
        return d
    def check(self,ok=True,**changes):
        r=review(**{**self.kw,**changes})
        self.assertIs(r["review_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        self.assertFalse(r["publication_allowed"])
        self.assertFalse(r["independent_oos_proven"])
        if not ok:self.assertNotIn("evaluation",r)
        return r
    def test_complete_private_evaluation(self):
        r=self.check()
        self.assertEqual(r["evaluation"]["paired_candidates"],1)
        self.assertTrue(r["selected_roster_locally_verified"])
        self.assertNotIn("raw_input",str(r))
    def test_pending_secondary(self):
        r=self.check(secondary_shas=[])
        self.assertEqual(r["evaluation"]["paired_candidates"],0)
        self.assertEqual(r["evaluation"]["unsettled_or_excluded"],1)
    def test_duplicate_digest_and_cross_source(self):
        self.check(False,run_shas=[self.run_id]*2)
        self.check(False,secondary_shas=[self.p])
    def test_tampered_run(self):
        f=self.store/(self.run_id+".json")
        f.write_bytes(f.read_bytes()+b" ")
        self.check(False)
    def test_permissions(self):
        (self.results/(self.p+".json")).chmod(0o644)
        self.check(False)
    def test_symlink(self):
        f=self.store/(self.run_id+".json")
        target=self.store/"renamed";f.rename(target);f.symlink_to(target)
        self.check(False)
    def test_runtime_guard(self):
        self.check(False,authorized=False)
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"}):
            self.check(False)
            r=collect(repository=self.repo,store=self.store,league="bundesliga",authorized=True)
            self.assertFalse(r["collection_saved"])
    def test_missing_credentials_no_provider_call(self):
        with patch("ops.research_private_runtime_v52.pilot") as pilot:
            r=collect(repository=self.repo,store=self.store,league="bundesliga",authorized=True)
            self.assertEqual(r["reason"],"NOT_CONFIGURED")
            pilot.assert_not_called()
    def test_collection_requires_private_store(self):
        with patch("ops.research_private_runtime_v52.pilot") as pilot:
            r=collect(repository=self.repo,store=None,league="bundesliga",authorized=True)
            self.assertFalse(r["collection_saved"])
            pilot.assert_not_called()
    def test_collection_delegates_to_persistent_pilot(self):
        with patch.dict(os.environ,{"PROPLINE_API_KEY":"synthetic"}),patch(
            "ops.research_private_runtime_v52.pilot",return_value={
                "private_run_saved":True,"private_run_sha256":self.run_id,
                "local_receipts":1,"acquisition":{"requests_attempted":2}}) as pilot:
            r=collect(repository=self.repo,store=self.store,league="bundesliga",authorized=True)
            self.assertTrue(r["collection_saved"])
            self.assertEqual(r["private_run_sha256"],self.run_id)
            pilot.assert_called_once_with(self.repo,"bundesliga",key="synthetic",private_store=self.store)
            self.assertNotIn("synthetic",str(r))

if __name__=="__main__":unittest.main()
