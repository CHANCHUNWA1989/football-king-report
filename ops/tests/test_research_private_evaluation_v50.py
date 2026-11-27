import unittest
import json
from math import log
from ops.research_private_evaluation_v50 import evaluate,metrics,paired
from ops.tests.test_research_private_settlement_v49 import inputs
from ops.tests.test_research_archive_score_recovery_v14 import encode
class PrivateEvaluationTests(unittest.TestCase):
    def test_paired_same_fixture(self):
        raw,p,s,now=inputs()
        r=evaluate([raw],[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["paired_candidates"],1)
        self.assertTrue(all(m["n"]==1 for m in r["models"].values()))
        receipt=json.loads(raw)["packets"][0]["receipt"]
        w=receipt["candidate"]["weight"]
        self.assertEqual(receipt["support"],[1,1,1,1])
        self.assertGreater(w,0)
        self.assertAlmostEqual(w,.005)
        m=receipt["market_p"];a=receipt["model_p"]
        expected=[(1-w)*q+w*p for p,q in zip(a,m)]
        for actual,p in zip(receipt["candidate"]["p"],expected):
            self.assertAlmostEqual(actual,p)
        self.assertAlmostEqual(r["mean_adaptive_weight"],w)
        self.assertEqual(r["zero_weight_count"],0)
        from ops.research_replay_attribution_v36 import losses
        saved_delta=losses(receipt["candidate"]["p"],0)[0]-losses(m,0)[0]
        self.assertAlmostEqual(saved_delta,log(m[0]/expected[0]))
        self.assertNotAlmostEqual(saved_delta,0)
        self.assertAlmostEqual(r["paired_vs_market"]["adaptive"]["log_loss_delta"],
                               log(m[0]/expected[0]))
        self.assertAlmostEqual(r["paired_vs_market"]["adaptive"]["brier_delta"],
                               sum((v-int(i==0))**2 for i,v in enumerate(expected))-
                               sum((v-int(i==0))**2 for i,v in enumerate(m)))
        self.assertFalse(r["independent_oos_proven"])
        self.assertEqual(r["authenticated_samples"],0)
    def test_zero_weight_equal_market(self):
        from ops.research_market_fusion_v37 import candidate
        m=[.4,.3,.3]
        c=candidate([.6,.2,.2],m,support=[1,1,1,0],market_age_seconds=120)
        self.assertEqual(c["weight"],0)
        r=paired([{"forecast_day":"2026-11-28","market":m,"adaptive":c["p"],"y":0}],"adaptive")
        self.assertAlmostEqual(r["log_loss_delta"],0)
        self.assertAlmostEqual(r["brier_delta"],0)

    def test_missing_results_no_fake_metrics(self):
        raw,p,s,now=inputs()
        r=evaluate([raw],[("p",encode(p))],[],as_of=now)
        self.assertEqual(r["paired_candidates"],0)
        self.assertEqual(r["unsettled_or_excluded"],1)
        self.assertIsNone(r["models"]["market"]["accuracy"])
    def test_empty_cohort(self):
        r=evaluate([],[],[],as_of="2026-11-29T00:00:00Z")
        self.assertEqual(r["submitted_fixtures"],0)
        self.assertIsNone(r["candidate_coverage"])
    def test_duplicate_run(self):
        raw,p,s,now=inputs()
        with self.assertRaises(ValueError):evaluate([raw,raw],[],[],as_of=now)
    def test_rps_and_ties(self):
        r=metrics([{"market":[.5,.5,0],"y":0}],"market")
        self.assertEqual(r["accuracy"],0)
        self.assertEqual(r["unique_top_count"],0)
        self.assertAlmostEqual(r["rps"],.125)
        self.assertAlmostEqual(r["brier"],.5)
    def test_descriptive_interval(self):
        rows=[{"forecast_day":str(i//3),"market":[.4,.3,.3],"adaptive":[.5,.25,.25],"y":0} for i in range(30)]
        r=paired(rows,"adaptive")
        self.assertLess(r["log_loss_delta"],0)
        self.assertEqual(r["interval"]["status"],"DESCRIPTIVE_DAY_CLUSTER_BOOTSTRAP")
        self.assertAlmostEqual(r["interval"]["lower"],r["log_loss_delta"])
        self.assertEqual(paired(rows[:29],"adaptive")["interval"]["status"],"INSUFFICIENT_SAMPLE")
