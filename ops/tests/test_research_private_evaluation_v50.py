import unittest
from ops.research_private_evaluation_v50 import evaluate,metrics,paired
from ops.tests.test_research_private_settlement_v49 import inputs
from ops.tests.test_research_archive_score_recovery_v14 import encode
class PrivateEvaluationTests(unittest.TestCase):
    def test_paired_same_fixture(self):
        raw,p,s,now=inputs()
        r=evaluate([raw],[("p",encode(p))],[("s",encode(s))],as_of=now)
        self.assertEqual(r["paired_candidates"],1)
        self.assertTrue(all(m["n"]==1 for m in r["models"].values()))
        # The adaptive forecast is not generally identical to the market baseline.\n        # Compare the reported paired delta to the actual same-fixture losses.\n        from ops.research_replay_attribution_v36 import losses\n        from ops.research_private_run_store_v48 import verify_run\n        import json\n        receipt=json.loads(raw)["packets"][0]["receipt"]\n        y=0  # Synthetic dual-publisher result is a home win.\n        expected=losses(receipt["candidate"]["p"],y)[0]-losses(receipt["market_p"],y)[0]\n        self.assertAlmostEqual(r["paired_vs_market"]["adaptive"]["log_loss_delta"],expected)\n        self.assertNotAlmostEqual(expected,0)
        self.assertFalse(r["independent_oos_proven"])
        self.assertEqual(r["authenticated_samples"],0)
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
