"""Existing settlement cross-checks for REAL 2026 3-market OOS pipeline."""
import math
import unittest

from ops.real_2026_three_market_oos import (
    total_grade, _distribution, _score, _baseline, evaluate, audit,
    MARKETS, TYPES, CLASSES_1X2, SCHEMA,
)
from ops.asian_handicap_research import grade as handicap_grade
from ops.all_market_scenarios import ah_scenario, total_scenario


class ThreeMarketEvidenceTests(unittest.TestCase):
    def test_exact_goal_line_over_three_half_win_on_275(self):
        for h,a in ((3,0),(2,1),(1,2),(0,3)):
            self.assertEqual(total_grade(h,a,"OVER",2.75),"HALF_WIN")
            self.assertEqual(total_grade(h,a,"UNDER",2.75),"HALF_LOSS")

    def test_ou_quarter_line_325_three_is_half_loss_over_and_halfwin_under(self):
        self.assertEqual(total_grade(2,1,"OVER",3.25),"HALF_LOSS")
        self.assertEqual(total_grade(2,1,"UNDER",3.25),"HALF_WIN")

    def test_goal_total_over_275_two_loses_four_wins(self):
        for h,a in ((0,0),(0,2),(1,1)):
            self.assertEqual(total_grade(h,a,"OVER",2.75),"FULL_LOSS")
        for h,a in ((4,0),(2,2),(1,3)):
            self.assertEqual(total_grade(h,a,"OVER",2.75),"FULL_WIN")

    def test_handicap_away_plus_quarter_draw_halfwin(self):
        self.assertEqual(handicap_grade(1,1,"AWAY",.25),"HALF_WIN")
        self.assertEqual(handicap_grade(1,1,"HOME",-.25),"HALF_LOSS")

    def test_total_grade_wrong_score_or_market_side_fails(self):
        for h,a,side in ((True,2,"OVER"),(-1,0,"OVER"),
                         (26,0,"OVER"),(1,1,"INVALID")):
            with self.subTest(h=h,a=a,side=side):
                with self.assertRaises(ValueError):
                    total_grade(h,a,side,2.75)

    def test_scenarios_share_existing_distribution_no_new_math(self):
        for market in MARKETS:
            p=_distribution(1.44,1.22,market)
            self.assertAlmostEqual(sum(p.values()),1,places=5)
            self.assertEqual(set(p),set(TYPES))
            expected=(ah_scenario(1.44,1.22,market[2],market[3])
                      if market[1]=="AH" else
                      total_scenario(1.44,1.22,side=market[2],line=market[3]))
            self.assertEqual(p,expected["settlement_probabilities"])
            self.assertFalse(expected["positive_expected_value_verified"])

    def test_first_observed_real_outcome_loss_score_one_hot(self):
        classes=CLASSES_1X2
        b,l=_score({"HOME":.6,"DRAW":.3,"AWAY":.1},"AWAY",classes)
        self.assertAlmostEqual(b,.6**2+.3**2+(.1-1)**2)
        self.assertAlmostEqual(l,-math.log(.1))

    def test_baseline_never_consults_2026_truth(self):
        train=[{"score_ft":[1,1]}]*5+[{"score_ft":[2,0]}]*5
        b=_baseline(train,"1X2")
        self.assertAlmostEqual(sum(b.values()),1)
        self.assertGreater(b["AWAY"],0)  # Jeffreys-smoothed unknown class

    def test_train_test_date_boundary_error(self):
        def row(d):return {"date":d,"home":"A","away":"B","score_ft":[1,0]}
        training=[row("2025-06-01")]*201
        heldout=[row("2026-06-01")]*151
        training[-1]=row("2026-01-01")
        with self.assertRaisesRegex(ValueError,"INVALID_SEPARATE_YEAR_COHORT"):
            evaluate(training,heldout)

    def test_duplicate_event_in_raw_loader_is_fail_closed(self):
        def fail():
            raise OSError("private upstream error with forbidden text")
        report=audit(source_reader=fail)
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["reason"],"TRUE_REAL_THREE_MARKET_HOLDOUT_UNAVAILABLE")
        self.assertNotIn("forbidden text",str(report))
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_no_bookmaker_market_price_claim_can_be_made_from_data(self):
        def fail():
            raise OSError("missing")
        r=audit(source_reader=fail)
        self.assertEqual(r["certified_prospective_three_market_samples"],0)
        self.assertFalse(r["positive_ev_verified"])

    def test_no_outcome_label_leak_in_scoring(self):
        b1,l1=_score({"FULL_WIN":.4,"HALF_WIN":.1,
                      "PUSH":.1,"HALF_LOSS":.1,"FULL_LOSS":.3},
                     "FULL_WIN",TYPES)
        b2,l2=_score({"FULL_WIN":.4,"HALF_WIN":.1,
                      "PUSH":.1,"HALF_LOSS":.1,"FULL_LOSS":.3},
                     "FULL_LOSS",TYPES)
        self.assertNotEqual((b1,l1),(b2,l2))


if __name__=="__main__":
    unittest.main()
