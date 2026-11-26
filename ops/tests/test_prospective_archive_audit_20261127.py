import unittest
from copy import deepcopy
from ops.prospective_archive_audit_20261127 import audit,overlap,canonical_manifest,digest,seal,GENESIS

ALIASES={"feed-a":"match-1","feed-b":"match-1","feed-c":"match-2","feed-d":"match-3"}
MANIFEST={"frozen_at":"2026-01-01T00:00:00Z","baseline_id":"base","challenger_id":"new",
          "fixtures":[{"fixture_id":"feed-a","decision_at":"2026-01-03T00:00:00Z"},
                      {"fixture_id":"feed-c","decision_at":"2026-01-04T00:00:00Z"}]}

def entries():
    md=digest(canonical_manifest(MANIFEST,ALIASES))
    return [{"fixture_id":f,"model_id":model,"manifest_sha256":md,
             "issued_at":"2026-01-02T00:00:00Z","features_through":"2026-01-01T12:00:00Z",
             "trained_through":"2025-12-31T00:00:00Z","probabilities":[.4,.3,.3]}
            for f in ("feed-a","feed-c") for model in ("base","new")]

def chain(es):
    out=[];prev=GENESIS
    for e in es:
        r=seal(e,prev);out.append(r);prev=r["sha256"]
    return out,prev

class ArchiveTests(unittest.TestCase):
    def test_complete_never_authorizes(self):
        rows,head=chain(entries())
        r=audit(MANIFEST,rows,ALIASES,{"old":["feed-d"]},head)
        self.assertEqual(r["status"],"STRUCTURAL_REVIEW_REQUIRED")
        self.assertEqual(r["observed_forecasts"],4)
        for k in ("promotion_authorized","external_anchor_authenticated","prospective_verified"):
            self.assertFalse(r[k])
    def test_overlap_alias_partial(self):
        r=overlap(["feed-a","feed-c"],{"old":["feed-b","feed-d"]},ALIASES)
        self.assertEqual(r["overlap_count"],1)
        self.assertEqual(r["overlaps"],{"old":["match-1"]})
        rows,head=chain(entries())
        self.assertIn("KNOWN_COHORT_OVERLAP",audit(MANIFEST,rows,ALIASES,{"old":["feed-b"]},head)["reasons"])
        with self.assertRaises(ValueError): overlap(["feed-a","feed-b"],{},ALIASES)
        with self.assertRaises(ValueError): overlap(["unknown"],{},ALIASES)
    def test_canonical_manifest(self):
        m=deepcopy(MANIFEST);m["fixtures"].reverse()
        m["fixtures"][1]["fixture_id"]="feed-b"
        self.assertEqual(digest(canonical_manifest(m,ALIASES)),digest(canonical_manifest(MANIFEST,ALIASES)))
    def test_tamper_delete_reseal(self):
        rows,head=chain(entries())
        rows[0]["entry"]["probabilities"]=[.3,.3,.4]
        with self.assertRaises(ValueError): audit(MANIFEST,rows,ALIASES,{},head)
        altered=entries();altered[0]["probabilities"]=[.3,.3,.4]
        rows,_=chain(altered)
        self.assertIn("ANCHOR_MISMATCH",audit(MANIFEST,rows,ALIASES,{},head)["reasons"])
        rows,_=chain(entries()[:-1])
        self.assertIn("INCOMPLETE_PAIRED_ARCHIVE",audit(MANIFEST,rows,ALIASES,{},head)["reasons"])
    def test_invalid_fields(self):
        for key,value in [("issued_at","2026-01-05T00:00:00Z"),("trained_through","2026-01-02T00:00:00Z"),
                          ("features_through","2026-01-03T00:00:00Z"),("manifest_sha256","x"),
                          ("probabilities",[.4,.4,.4]),("probabilities",[True,0,0]),
                          ("model_id","unknown"),("fixture_id","feed-d")]:
            es=entries();es[0][key]=value;rows,head=chain(es)
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                audit(MANIFEST,rows,ALIASES,{},head)
        es=entries();es[1]=deepcopy(es[0]);rows,head=chain(es)
        with self.assertRaises(ValueError): audit(MANIFEST,rows,ALIASES,{},head)
    def test_overlap_matrix(self):
        from itertools import combinations
        subsets=[list(v) for n in range(1,4) for v in combinations(("feed-a","feed-c","feed-d"),n)]
        for a in subsets:
            for b in subsets:
                self.assertEqual(overlap(a,{"prior":b},ALIASES)["overlap_count"],len(set(a)&set(b)))

if __name__=="__main__": unittest.main()
