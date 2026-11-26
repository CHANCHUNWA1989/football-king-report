import unittest
from datetime import datetime,timedelta,timezone
from copy import deepcopy
from ops.live_paired_holdout_20261127 import evaluate_holdout

def cohort(weeks=20, per_week=5):
    freeze=datetime(2026,1,1,tzinfo=timezone.utc)
    manifest={"frozen_at":freeze.isoformat(),"baseline_id":"b1","challenger_id":"c1","fixtures":[]}
    rows=[]
    for w in range(weeks):
        for j in range(per_week):
            t=freeze+timedelta(days=7*(w+1),hours=j)
            fid=f"{w}-{j}"
            entry={"fixture_id":fid,"decision_at":t.isoformat()}
            manifest["fixtures"].append(entry)
            r=dict(entry,baseline_id="b1",challenger_id="c1",
                   settled_at=(t+timedelta(hours=2)).isoformat(),
                   baseline=[.3,.4,.3],challenger=[.2,.6,.2],outcome=1)
            for name in ("baseline","challenger"):
                r[name+"_trained_through"]=freeze.isoformat()
                r[name+"_issued_at"]=(t-timedelta(seconds=10)).isoformat()
                r[name+"_features_through"]=(t-timedelta(seconds=20)).isoformat()
            rows.append(r)
    return manifest,rows

class HoldoutTests(unittest.TestCase):
    def test_complete(self):
        m,r=cohort()
        a=evaluate_holdout(m,r)
        self.assertEqual(a["n"],100)
        self.assertEqual(a["utc_weeks"],20)
        self.assertEqual(a["bootstrap_draws"],2000)
        self.assertTrue(a["primary_interval_below_zero"])
        self.assertFalse(a["out_of_sample_verified"])
        self.assertFalse(a["confidence_interval_verified"])
        self.assertEqual(a["deployment"],"HOLD")
        self.assertEqual(a["recommendations"],"DISABLED")
        self.assertEqual(a,evaluate_holdout(m,r))
    def test_identical_models_predictions(self):
        m,r=cohort()
        for row in r:
            row["challenger"]=row["baseline"][:]
        a=evaluate_holdout(m,r)
        self.assertFalse(a["primary_interval_below_zero"])
        self.assertTrue(all(x==[0,0] for x in a["intervals"].values()))
    def test_small_samples(self):
        for weeks,per_week in [(19,6),(20,4),(1,100),(1,1)]:
            m,r=cohort(weeks,per_week)
            a=evaluate_holdout(m,r)
            self.assertEqual(a["status"],"INSUFFICIENT_SAMPLE")
            self.assertIsNone(a["intervals"])
    def test_selection_and_leakage(self):
        m,r=cohort(2,2)
        with self.assertRaises(ValueError): evaluate_holdout(m,r[:-1])
        with self.assertRaises(ValueError): evaluate_holdout(m,r+[r[0]])
        for patch in [{"fixture_id":"unexpected"},{"challenger_id":"wrong"},
                      {"challenger_trained_through":"2026-01-02T00:00:00Z"},
                      {"baseline_issued_at":"2025-12-31T00:00:00Z"},
                      {"decision_at":"2026-01-09T00:00:00Z"}]:
            bad=deepcopy(r); bad[0].update(patch)
            with self.subTest(patch=patch),self.assertRaises(ValueError):
                evaluate_holdout(m,bad)
    def test_manifest_digest(self):
        m,r=cohort(2,2)
        a=evaluate_holdout(m,r)
        m["fixtures"].reverse()
        self.assertEqual(a["manifest_sha256"],evaluate_holdout(m,r)["manifest_sha256"])
        m["fixtures"].append(deepcopy(m["fixtures"][0]))
        with self.assertRaises(ValueError): evaluate_holdout(m,r)

if __name__=="__main__": unittest.main()
