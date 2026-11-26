import unittest
from copy import deepcopy
from math import log
from ops.prospective_archive_audit_20261127 import canonical_manifest,seal,GENESIS
from ops.prospective_score_archive_v2_20261127 import SCHEMA,manifest_hash,derive,losses,uncertainty,review,grid_from_cells
from ops.research_promotion_triage_20261127 import METRICS

def chain(entries):
    rows=[];head=GENESIS
    for e in entries:
        r=seal(e,head);rows.append(r);head=r["sha256"]
    return rows,head

def packet():
    aliases={"a":"match1","b":"match1"}
    manifest={"frozen_at":"2026-01-01T00:00:00Z","baseline_id":"base","challenger_id":"new",
              "fixtures":[{"fixture_id":"a","decision_at":"2026-01-03T00:00:00Z"}]}
    md=manifest_hash(canonical_manifest(manifest,aliases))
    forecasts=[{"schema":SCHEMA,"fixture_id":"a","model_id":model,"manifest_sha256":md,
                "issued_at":"2026-01-02T00:00:00Z","features_through":"2026-01-01T12:00:00Z",
                "trained_through":"2025-12-31T00:00:00Z","score_cells":cells}
               for model,cells in [("base",[[2,1,.4],[0,0,.3],[0,5,.3]]),
                                   ("new",[[2,1,.6],[0,0,.2],[0,5,.2]])]]
    settlements=[{"fixture_id":"b","manifest_sha256":md,"settled_at":"2026-01-03T02:00:00Z",
                  "observed_at":"2026-01-03T02:05:00Z","score":[2,1],"status":"FULL_TIME_REGULATION"}]
    return manifest,aliases,forecasts,settlements

def run(m,a,f,s,prior=None):
    ff,fh=chain(f);ss,sh=chain(s)
    return review(m,ff,ss,a,prior or {},fh,sh,"2026-01-04T00:00:00Z")

class ScoreArchiveTests(unittest.TestCase):
    def test_derived_five_metrics(self):
        r=run(*packet())
        self.assertEqual(r["metrics"]["n"],1)
        self.assertEqual(set(r["metrics"]["deltas"]),set(METRICS))
        self.assertAlmostEqual(r["metrics"]["deltas"]["log_loss"],log(.4/.6))
        self.assertAlmostEqual(r["metrics"]["deltas"]["exact_score"],log(.4/.6))
        self.assertAlmostEqual(r["metrics"]["deltas"]["tail_brier"],.04-.09)
        self.assertIsNone(r["metrics"]["intervals"])
        self.assertFalse(r["promotion_authorized"])
        self.assertEqual(r["status"],"HOLD")
        self.assertNotIn("SCORE_DISTRIBUTION_GUARDRAILS_MISSING",r["reasons"])
    def test_markets_from_grid(self):
        g,m=derive([[0,0,.2],[2,1,.5],[3,2,.3]])
        for a,b in zip(m["one_x_two"],[.8,.2,0]): self.assertAlmostEqual(a,b)
        self.assertAlmostEqual(m["five_plus"],.3)
        self.assertAlmostEqual(m["both_teams_score"],.8)
        self.assertAlmostEqual(m["totals"][1]["over"]["half_win"],.5)
        self.assertAlmostEqual(m["totals"][1]["over"]["full_win"],.3)
        self.assertAlmostEqual(m["handicaps"][0]["home"]["full_loss"],1)
        self.assertAlmostEqual(losses(g,m,[0,5])[3],-log(1e-15))
    def test_invalid_grid(self):
        for cells in ([],[[0,0,.9]],[[0,0,.5],[0,0,.5]],[[31,0,1]],[[True,0,1]],
                      [[0,0,True]],[[0,0,float("nan")]],[[0,0,-.1],[1,0,1.1]]):
            with self.subTest(cells=cells),self.assertRaises(ValueError): grid_from_cells(cells)
    def test_overlap_and_integrity(self):
        m,a,f,s=packet()
        self.assertIn("KNOWN_COHORT_OVERLAP",run(m,a,f,s,{"old":["b"]})["reasons"])
        self.assertIsNone(run(m,a,f[:1],s)["metrics"])
        self.assertIsNone(run(m,a,f,[])["metrics"])
        ff,fh=chain(f);ss,sh=chain(s)
        ff[0]["entry"]["score_cells"]=[[0,0,1]]
        self.assertIsNone(review(m,ff,ss,a,{},fh,sh,"2026-01-04T00:00:00Z")["metrics"])
        ff,_=chain([r["entry"] for r in ff])
        self.assertIsNone(review(m,ff,ss,a,{},fh,sh,"2026-01-04T00:00:00Z")["metrics"])
    def test_schema_and_chronology(self):
        for key,v in [("schema","OLD"),("issued_at","2026-01-04T00:00:00Z"),
                      ("trained_through","2026-01-02T00:00:00Z"),("features_through","2026-01-03T00:00:00Z")]:
            m,a,f,s=packet();f[0][key]=v
            self.assertIsNone(run(m,a,f,s)["metrics"])
    def test_cluster_bootstrap(self):
        pairs=[((2026,w),(-.1,-.2,-.3,-.4,-.5)) for w in range(1,21) for _ in range(5)]
        a=uncertainty(pairs)
        self.assertEqual(a,uncertainty(pairs))
        self.assertEqual(a[2],20)
        for k,v in a[0].items():
            for bound in a[1][k]: self.assertAlmostEqual(v,bound)
        self.assertIsNone(uncertainty(pairs[:95])[1])

if __name__=="__main__": unittest.main()
