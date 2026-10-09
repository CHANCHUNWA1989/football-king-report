"""No data => no accuracy claims; metrics use only genuinely settled samples."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from research_center import metrics,calibration,score,LEAGUES


class ResearchCenterTests(unittest.TestCase):
    def test_zero_samples_do_not_invent_accuracy(self):
        self.assertIsNone(metrics([]))
        self.assertEqual(len(LEAGUES),6)

    def test_same_case_ab_comparison(self):
        r={"league":"epl","p":[.5,.25,.25],"m":[.3,.3,.4],
           "ab":[.45,.28,.27],"y":0,"kickoff_utc":"2026-10-10T12:00:00+00:00"}
        result=metrics([r])
        self.assertEqual(result["settled_games"],1)
        self.assertEqual(result["ab_research"]["same_case_count"],1)
        self.assertFalse(result["ab_research"]["promoted"])
        self.assertTrue(result["descriptive_only"])

    def test_calibration_bins_count_samples_three_times(self):
        r={"p":[.6,.3,.1],"y":2}
        bins=calibration([r])
        self.assertEqual(sum(sum(b["n"] for b in x["bins"]) for x in bins),3)

    def test_invalid_probabilities_rejected(self):
        with self.assertRaises(ValueError):
            score([.9,.9,-.8],1)


if __name__=="__main__":
    unittest.main()
