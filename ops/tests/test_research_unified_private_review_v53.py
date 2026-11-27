import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from ops.research_unified_private_review_v53 import run,load_live_request
from ops.research_prospective_fusion_v38 import sha
from ops.tests.test_research_private_settlement_v49 import inputs
from ops.tests.test_research_archive_score_recovery_v14 import encode
from ops.tests.test_research_unified_market_benchmark_v44 import fixture

ROOT=Path(__file__).resolve().parents[2]

def live_doc():
    kw=fixture();kw.pop("as_of")
    for execution in kw["executions"]:
        execution.pop("root")
        for case in execution["live_cases"].values():
            args=case["inputs"]
            args["prematch_raw"]=args["prematch_raw"].hex()
            args["live_raw_captures"]=[x.hex() for x in args["live_raw_captures"]]
    return kw

class UnifiedPrivateReviewTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.store=root/"runs";self.store.mkdir(mode=0o700)
        self.results=root/"results";self.results.mkdir(mode=0o700)
        self.live=root/"live";self.live.mkdir(mode=0o700)
        raw,p,s,now=inputs()
        self.kw=dict(repository=ROOT,store=self.store,result_store=self.results,
            live_store=self.live,live_sha=self.put(self.live,encode(live_doc())),
            run_shas=[self.put(self.store,raw)],primary_shas=[self.put(self.results,encode(p))],
            secondary_shas=[self.put(self.results,encode(s))],as_of=now,authorized=True)
        env=patch.dict(os.environ,{"GITHUB_ACTIONS":"false"});env.start();self.addCleanup(env.stop)
    def put(self,directory,raw):
        d=sha(raw);p=directory/(d+".json");p.write_bytes(raw);p.chmod(0o600)
        return d
    def check(self,ok=True,**changes):
        r=run(**{**self.kw,**changes})
        self.assertIs(r["review_passed"],ok,r)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["authenticated_samples"],0)
        for k in ("publication_allowed","independent_oos_proven","model_promotion_allowed",
                  "cohorts_pooled","cross_cohort_ranking_allowed"):
            self.assertIs(r[k],False)
        if not ok:
            self.assertNotIn("private_prematch_evaluation",r)
            self.assertNotIn("live_linked_prematch_benchmark",r)
        return r
    def test_end_to_end_distinct_cohorts(self):
        r=self.check()
        self.assertEqual(r["private_prematch_evaluation"]["paired_candidates"],1)
        self.assertEqual(r["live_linked_prematch_benchmark"]["n"],1)
        self.assertNotIn("combined_accuracy",r)
        self.assertEqual(r,self.check())
    def test_unresolved_private_results(self):
        r=self.check(secondary_shas=[])
        self.assertEqual(r["private_prematch_evaluation"]["paired_candidates"],0)
        self.assertEqual(r["live_linked_prematch_benchmark"]["n"],1)
    def test_live_bytes_changed(self):
        p=self.live/(self.kw["live_sha"]+".json");p.write_bytes(p.read_bytes()+b" ")
        self.check(False)
    def test_invalid_live_final(self):
        d=live_doc();d["finals"]["synthetic"]["final_observations"][1]["home"]=30
        self.check(False,live_sha=self.put(self.live,encode(d)))
    def test_invalid_private_run(self):
        self.check(False,run_shas=["0"*64])
    def test_runtime_guard(self):
        self.check(False,authorized=False)
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"}):self.check(False)
    def test_shared_store_rejected(self):
        self.check(False,live_store=self.store)
    def test_strict_request_schema_and_hex(self):
        d=live_doc();d["as_of"]="2026-11-29T00:00:00Z"
        with self.assertRaises(ValueError):load_live_request(encode(d))
        d=live_doc()
        d["executions"][0]["live_cases"]["synthetic"]["inputs"]["prematch_raw"]="aa bb"
        with self.assertRaises(ValueError):load_live_request(encode(d))

if __name__=="__main__":unittest.main()
