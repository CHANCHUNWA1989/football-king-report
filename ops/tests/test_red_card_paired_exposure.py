"""Synthetic-only red-card paired exposure research tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from red_card_paired_exposure import summarize


def bucket(cards, minutes, xg, shots=(3, 3)):
    return {"dismissals": list(cards), "elapsed_minutes": minutes,
            "xg": list(xg), "shots": list(shots)}


def fixture(mid=1, away=False, post=30):
    return {"match_id":mid,"regulation_cards":1,"buckets":[
        bucket((0,0),60,(1.2,.6) if not away else (.6,1.2)),
        bucket((0,1) if away else (1,0),post,(.9,.2) if away else (.2,.9))]}


class PairedExposureTests(unittest.TestCase):
    def test_home_away_orientation_and_exposure_weighting(self):
        r=summarize([fixture(),fixture(2,True)])
        self.assertEqual(r["accepted_matches"],2)
        self.assertAlmostEqual(r["dismissed_team"]["pre_xg_per_90"],1.8)
        self.assertAlmostEqual(r["dismissed_team"]["post_xg_per_90"],.6)
        self.assertAlmostEqual(r["opponent"]["pre_xg_per_90"],.9)
        self.assertAlmostEqual(r["opponent"]["post_xg_per_90"],2.7)
        self.assertFalse(r["causal_effect_estimated"])
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def test_exposure_weighting_not_average_of_individual_rates(self):
        a,b=fixture(),fixture(2,post=20)
        b["buckets"][0]["elapsed_minutes"]=70
        self.assertAlmostEqual(summarize([a,b])["dismissed_team"]["post_xg_per_90"],.72)

    def test_duplicate_group_never_selected(self):
        self.assertEqual(summarize([fixture(),fixture()])["accepted_matches"],0)
        self.assertEqual(summarize([fixture(),fixture()])["rejected"]["DUPLICATE_MATCH"],2)

    def test_short_or_multiple_dismissals_do_not_enter_single_card_cohort(self):
        a=fixture(post=10)
        a["buckets"][0]["elapsed_minutes"]=80
        b=fixture(2);b["regulation_cards"]=2
        r=summarize([a,b])
        self.assertEqual(r["accepted_matches"],0)
        self.assertEqual(r["rejected"]["INSUFFICIENT_EXPOSURE"],1)
        self.assertEqual(r["rejected"]["NOT_SINGLE_DISMISSAL"],1)
        self.assertIsNone(r["dismissed_team"])

    def test_invalid_xg_and_exposure_fail_closed(self):
        for value in (float("nan"),-1,True,10):
            a=fixture();a["buckets"][1]["xg"][0]=value
            self.assertEqual(summarize([a])["accepted_matches"],0)
        a=fixture();a["buckets"][1]["elapsed_minutes"]=1000
        self.assertEqual(summarize([a])["accepted_matches"],0)

    def test_paired_bootstrap_identical_cases_and_order_invariance(self):
        rows=[fixture(i, i%2==0) for i in range(1,31)]
        a=summarize(rows)["uncertainty"]
        self.assertEqual(a,summarize(list(reversed(rows)))["uncertainty"])
        self.assertEqual(a["status"],"DESCRIPTIVE_INTERVAL_ONLY")
        self.assertEqual(a["replicates"],1000)
        bounds=a["rate_difference_intervals"]["dismissed_team"]
        self.assertAlmostEqual(bounds["lower"],-1.2)
        self.assertAlmostEqual(bounds["upper"],-1.2)
        self.assertFalse(a["inferentially_validated"])

    def test_small_sample_suppresses_interval(self):
        r=summarize([fixture(1),fixture(2)])
        self.assertEqual(r["uncertainty"]["status"],"INSUFFICIENT_SAMPLE")
        self.assertIsNone(r["uncertainty"]["rate_difference_intervals"])

    def test_exposure_threshold_sensitivity_and_leave_one_out(self):
        rows=[fixture(1),fixture(2,post=20)]
        rows[1]["buckets"][0]["elapsed_minutes"]=70
        r=summarize(rows)
        by={s["minimum_minutes_each_state"]:s for s in r["exposure_sensitivity"]}
        self.assertEqual(by[15]["matches"],2)
        self.assertEqual(by[20]["matches"],2)
        self.assertEqual(by[30]["matches"],1)
        self.assertAlmostEqual(by[30]["dismissed_team"]["rate_difference"],-1.2)
        bounds=r["influence"]["dismissed_team"]["leave_one_out_rate_difference_range"]
        self.assertAlmostEqual(bounds["lower"],-1.2)
        self.assertAlmostEqual(bounds["upper"],1.8-90*1.2/70)
        self.assertFalse(r["model_calibrated"])

    def test_equal_fixture_and_pooled_effects_distinct(self):
        a,b=fixture(),fixture(2,post=20)
        b["buckets"][0]["elapsed_minutes"]=70
        r=summarize([a,b])
        self.assertNotAlmostEqual(r["influence"]["dismissed_team"]["equal_fixture_mean_difference"],
                                  r["dismissed_team"]["rate_difference"])

    def test_sample_threshold_never_certifies(self):
        r=summarize([fixture(i) for i in range(1,31)])
        self.assertFalse(r["small_sample"])
        self.assertFalse(r["model_calibrated"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(r["status"],"HOLD")


if __name__=="__main__":
    unittest.main()
