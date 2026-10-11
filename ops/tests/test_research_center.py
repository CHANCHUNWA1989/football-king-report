"""No data => no accuracy claims; metrics use only genuinely settled samples."""
import sys
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

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            score([.9,.9,-.8],1)


if __name__=="__main__":
    unittest.main()
