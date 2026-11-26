import unittest
from copy import deepcopy
from math import log
from ops.prospective_archive_audit_20261127 import canonical_manifest,digest,seal,GENESIS
from ops.prospective_evidence_pipeline_20261127 import review

def chain(entries):
    rows=[];head=GENESIS
    for e in entries:
        row=seal(e,head);rows.append(row);head=row["sha256"]
    return rows,head

def packet():
    aliases={"a":"match1","b":"match1"}
    manifest={"frozen_at":"2026-01-01T00:00:00Z","baseline_id":"base","challenger_id":"new",
              "fixtures":[{"fixture_id":"a","decision_at":"2026-01-03T00:00:00Z"}]}
    md=digest(canonical_manifest(manifest,aliases))
    forecasts=[{"fixture_id":"a","model_id":model,"manifest_sha256":md,
                "issued_at":"2026-01-02T00:00:00Z","features_through":"2026-01-01T12:00:00Z",
                "trained_through":"2025-12-31T00:00:00Z","probabilities":p}
               for model,p in [("base",[.4,.3,.3]),("new",[.6,.2,.2])]]
    settlements=[{"fixture_id":"b","manifest_sha256":md,"settled_at":"2026-01-03T02:00:00Z",
                  "observed_at":"2026-01-03T02:05:00Z","score":[2,1],"status":"FULL_TIME_REGULATION"}]
    return manifest,aliases,forecasts,settlements

def run(m,a,f,s,prior=None):
    ff,fh=chain(f);ss,sh=chain(s)
    return review(m,ff,ss,a,prior or {},fh,sh,"2026-01-04T00:00:00Z")

class EvidencePipelineTests(unittest.TestCase):
    def test_derived_metrics_never_promote(self):
        r=run(*packet())
        self.assertAlmostEqual(r["metrics"]["mean_challenger_minus_baseline"]["log_loss"],log(.4/.6))
        self.assertEqual(r["metrics"]["n"],1)
        self.assertIn("SCORE_DISTRIBUTION_GUARDRAILS_MISSING",r["reasons"])
        self.assertFalse(r["promotion_authorized"])
        self.assertEqual(r["status"],"HOLD")
    def test_overlap_and_missing_pair(self):
        m,a,f,s=packet()
        self.assertIn("KNOWN_COHORT_OVERLAP",run(m,a,f,s,{"old":["b"]})["reasons"])
        self.assertIn("INCOMPLETE_PAIRED_ARCHIVE",run(m,a,f[:1],s)["reasons"])
    def test_invalid_settlements(self):
        for key,v in [("score",[True,0]),("score",[2,-1]),("score",[31,0]),("status","EXTRA_TIME"),
                      ("settled_at","2026-01-02T00:00:00Z"),("observed_at","2026-01-05T00:00:00Z"),
                      ("fixture_id","unknown"),("manifest_sha256","bad")]:
            m,a,f,s=packet();s[0][key]=v
            with self.subTest(key=key,v=v):
                self.assertEqual(run(m,a,f,s)["reasons"],["INVALID_EVIDENCE"])
        m,a,f,s=packet()
        for rows in ([],s+s):
            self.assertIsNone(run(m,a,f,rows)["metrics"])
    def test_anchor_and_tamper(self):
        m,a,f,s=packet();ff,fh=chain(f);ss,sh=chain(s)
        ss[0]["entry"]["score"]=[0,1]
        r=review(m,ff,ss,a,{},fh,sh,"2026-01-04T00:00:00Z")
        self.assertIsNone(r["metrics"])
        ss,_=chain([ss[0]["entry"]])
        r=review(m,ff,ss,a,{},fh,sh,"2026-01-04T00:00:00Z")
        self.assertIsNone(r["metrics"])
    def test_outcome_derived(self):
        m,a,f,s=packet();s[0]["score"]=[0,2]
        r=run(m,a,f,s)
        self.assertAlmostEqual(r["metrics"]["mean_challenger_minus_baseline"]["log_loss"],log(.3/.2))

if __name__=="__main__": unittest.main()
