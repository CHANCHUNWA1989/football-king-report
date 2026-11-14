"""No data => no accuracy claims; metrics use only genuinely settled samples."""
import sys
from copy import deepcopy
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_center import metrics,calibration,score,LEAGUES
from model_ab import MODEL as B_MODEL, candidate as b_candidate
from model_market_challenger import MODEL as C_MODEL, candidate as c_candidate


class ResearchCenterTests(unittest.TestCase):
    def test_zero_samples_do_not_invent_accuracy(self):
        self.assertIsNone(metrics([]))
        self.assertEqual(len(LEAGUES),6)

    def test_same_case_ab_comparison(self):
        r={"league":"epl","p":[.5,.25,.25],"m":[.3,.3,.4],
           "ab":b_candidate([.5,.25,.25]),"ab_model":B_MODEL,
           "y":0,"kickoff_utc":"2026-10-10T12:00:00+00:00"}
        result=metrics([r])
        self.assertEqual(result["settled_games"],1)
        self.assertEqual(result["ab_research"]["same_case_count"],1)
        self.assertFalse(result["ab_research"]["promoted"])
        self.assertTrue(result["descriptive_only"])

    def test_same_sealed_four_way_compares_exact_same_new_cases(self):
        original = [.70,.20,.10]
        market = [.30,.30,.40]
        row = {"league":"epl","p":original,"m":market,
               "ab":b_candidate(original),"ab_model":B_MODEL,
               "c":c_candidate(original,market),"c_model":C_MODEL,
               "y":2,"kickoff_utc":"2026-10-12T12:00:00+00:00"}
        earlier = dict(row)
        earlier.pop("c")
        earlier.pop("c_model")
        earlier["kickoff_utc"]="2026-10-10T12:00:00+00:00"
        result=metrics([row,earlier])
        self.assertEqual(result["settled_games"],2)
        self.assertEqual(result["ab_research"]["same_case_count"],2)
        self.assertEqual(result["market_anchored_c_research"]["same_sealed_case_count"],1)
        four=result["prospective_four_way_research"]
        self.assertEqual(four["same_sealed_case_count"],1)
        self.assertEqual(four["independent_week_blocks"],1)
        self.assertLess(four["market_log_loss"],four["c_log_loss"])
        self.assertLess(four["c_log_loss"],four["a_log_loss"])
        self.assertEqual(four["market_brier"],result["market_anchored_c_research"]["same_case_market_brier"])
        self.assertFalse(four["model_advantage_vs_market_proven"])
        self.assertFalse(four["eligible_for_betting_promotion"])

    def test_unsealed_b_does_not_fake_four_way_sample(self):
        p,m=[.65,.20,.15],[.48,.28,.24]
        row={"league":"bundesliga","p":p,"m":m,
             "ab":[.70,.15,.15],"ab_model":B_MODEL,
             "c":c_candidate(p,m),"c_model":C_MODEL,
             "y":0,"kickoff_utc":"2026-10-12T12:00:00+00:00"}
        outcome=metrics([row])
        self.assertEqual(outcome["prospective_four_way_research"]["same_sealed_case_count"],0)
        self.assertEqual(outcome["ab_research"]["same_case_count"],0)
        self.assertEqual(outcome["market_anchored_c_research"]["same_sealed_case_count"],1)

    def test_calibration_bins_count_samples_three_times(self):
        r={"p":[.6,.3,.1],"y":2}
        bins=calibration([r])
        self.assertEqual(sum(sum(b["n"] for b in x["bins"]) for x in bins),3)

    def test_classwise_ece_weights_samples_and_uses_unrounded_statistics(self):
        rows=[{"p":[.1,.2,.7],"y":0}, {"p":[.1,.2,.7],"y":2},
              {"p":[.9,.05,.05],"y":1}]
        report=calibration(rows)
        self.assertIn("expected_calibration_error", report[0])
        self.assertAlmostEqual(report[0]["expected_calibration_error"],1.7/3,places=7)
        self.assertAlmostEqual(report[1]["expected_calibration_error"],.45,places=7)
        self.assertAlmostEqual(report[2]["expected_calibration_error"],.15,places=7)
        precise=calibration([{"p":[.60004,.2,.19996],"y":0}])[0]
        self.assertEqual(precise["bins"][3]["forecast_mean"],.6)
        self.assertAlmostEqual(precise["expected_calibration_error"],.39996,places=8)

    def test_existing_bin_edges_keep_zero_and_one_in_their_original_bins(self):
        rows=[{"p":[p,1-p,0.0],"y":0} for p in (0.,.2,.4,.6,.8,1.)]
        report=calibration(rows)
        self.assertEqual([bucket["n"] for bucket in report[0]["bins"]],[1,1,1,1,2])
        self.assertIn("expected_calibration_error", report[0])
        self.assertAlmostEqual(report[0]["expected_calibration_error"],.5)

    def test_model_market_calibration_uses_same_matches_without_changing_inputs(self):
        rows=[{"league":"epl","p":[.8,.1,.1],"m":[.5,.25,.25],
               "y":y,"kickoff_utc":f"2026-10-{10+y}T12:00:00+00:00"} for y in (0,2)]
        original=deepcopy(rows)
        measured=metrics(rows)
        self.assertIn("calibration_audit",measured)
        audit=measured["calibration_audit"]
        self.assertEqual(audit["same_case_count"],2)
        self.assertEqual(audit["bin_count"],5)
        self.assertEqual(audit["model_macro_ece"],.266667)
        self.assertEqual(audit["market_macro_ece"],.166667)
        self.assertEqual(audit["market_minus_model_macro_ece"],-.1)
        for name in ("model","market"):
            self.assertEqual([sum(b["n"] for b in cls["bins"]) for cls in audit[name]],[2,2,2])
        self.assertFalse(audit["calibration_verified"])
        self.assertFalse(audit["results_independently_verified"])
        self.assertEqual(audit["production_recommendations"],"DISABLED")
        self.assertEqual(measured["model_brier"],.76)
        self.assertEqual(measured["market_brier"],.625)
        self.assertEqual(rows,original)

    def test_calibration_rejects_invalid_vectors_and_boolean_outcomes(self):
        cases=[{"p":[-.1,.5,.6],"y":0}, {"p":[True,0,0],"y":0},
               {"p":[.5,.5,.5],"y":0}, {"p":[.5,.3,.2],"y":True},
               {"p":[.5,.3,.2],"y":3}]
        for row in cases:
            with self.subTest(row=row),self.assertRaises(ValueError):
                calibration([row])

    def test_empty_classwise_calibration_does_not_claim_zero_error(self):
        self.assertIsNone(metrics([]))
        for item in calibration([]):
            self.assertIn("expected_calibration_error",item)
            self.assertIsNone(item["expected_calibration_error"])
            self.assertTrue(all(bucket["forecast_mean"] is None for bucket in item["bins"]))

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            score([.9,.9,-.8],1)



    def test_boolean_outcome_is_not_a_real_score(self):
        with self.assertRaises(ValueError):
            score([.2,.3,.5], True)
        with self.assertRaises(ValueError):
            score([.2,.3,.5], False)

    def test_four_way_sample_shortfall_is_explicit_not_certification(self):
        p,m=[.65,.20,.15],[.48,.28,.24]
        row={"league":"bundesliga","p":p,"m":m,
             "ab":b_candidate(p),"ab_model":B_MODEL,
             "c":c_candidate(p,m),"c_model":C_MODEL,
             "y":0,"kickoff_utc":"2026-10-12T12:00:00+00:00"}
        four=metrics([row])["prospective_four_way_research"]
        self.assertEqual(four["same_sealed_case_count"], 1)
        self.assertEqual(four["remaining_same_case_fixtures_to_300"],299)
        self.assertEqual(four["remaining_week_blocks_to_12"],11)
        self.assertFalse(four["minimum_four_leagues_with_40_met"])
        self.assertFalse(four["descriptive_coverage_thresholds_met"])
        self.assertFalse(four["model_advantage_vs_market_proven"])


if __name__=="__main__":
    unittest.main()
