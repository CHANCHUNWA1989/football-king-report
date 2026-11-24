"""Pure settlement mechanics tests; real 186-match audit runs separately."""
import unittest

from ops.real_2026_goals_275_audit import (
    aggregate, audit, score_over_275,
)

def sample(scores, *, base="2026-01-01"):
    return [{"date":base,"score_ft":list(v)} for v in scores]


class RealGoal275SettlementTests(unittest.TestCase):
    def test_zero_to_two_full_loss(self):
        for a,b in [(0,0),(0,1),(1,0),(1,1),(0,2),(2,0)]:
            self.assertEqual(score_over_275([a,b]),("FULL_LOSS",-1))

    def test_three_goals_wins_only_half_stake(self):
        for a,b in [(3,0),(2,1),(1,2),(0,3)]:
            code,net=score_over_275([a,b])
            self.assertEqual(code,"HALF_WIN")
            self.assertAlmostEqual(net,.39)

    def test_four_and_more_goals_full_win(self):
        for a,b in [(4,0),(2,2),(3,1),(7,2)]:
            code,net=score_over_275([a,b])
            self.assertEqual(code,"FULL_WIN")
            self.assertAlmostEqual(net,.78)

    def test_single_full_loss_is_negative_one_unit(self):
        report=aggregate(sample([(1,0)]))
        self.assertEqual(report["hypothetical_uniform_flat_stake_roi"],-1)

    def test_three_goal_halfwin_is_not_push_or_fullwin(self):
        report=aggregate(sample([(2,1)]))
        self.assertAlmostEqual(report["hypothetical_uniform_flat_stake_roi"],.39)

    def test_identical_2026_true_score_counts_from_separate_real_source_are_20pct_loss(self):
        # 186 REAL completed European international outcomes counted from
        # pinned martj42 CSV. This is a fixed settlement-invariant proof,
        # NOT a synthetic test of model edge or a fake sports-book quote.
        entries=sample([(0,2)]*92+[(1,2)]*50+[(2,2)]*44)
        r=aggregate(entries)
        self.assertEqual(r["matches"],186)
        self.assertEqual((r["total_score_0_2"],r["total_score_exactly_3"],
                          r["total_score_4_or_more"]), (92,50,44))
        self.assertAlmostEqual(r["hypothetical_uniform_flat_stake_roi"],-.205269,places=5)
        self.assertAlmostEqual(
            r["empirical_fixed_price_breakeven_decimal_no_fees"],2.333333,places=6)
        self.assertFalse(r["historical_tradable_odds_collected"])

    def test_historic_2025_fixed_counts_are_not_used_to_train_2026_betting_model(self):
        entries=sample([(1,1)]*106+[(1,2)]*44+[(2,2)]*110,
                       base="2025-06-01")
        r=aggregate(entries)
        self.assertEqual(r["matches"],260)
        self.assertAlmostEqual(r["hypothetical_uniform_flat_stake_roi"],-.011692,places=5)

    def test_different_illustrative_odds_do_not_change_goal_occurrence(self):
        entries=sample([(1,1),(1,2),(2,2)])
        a,b=(aggregate(entries,decimal=x) for x in (1.78,2.0))
        self.assertEqual(a["total_score_0_2"],b["total_score_0_2"])
        self.assertNotEqual(a["hypothetical_uniform_flat_stake_roi"],
                            b["hypothetical_uniform_flat_stake_roi"])

    def test_no_eligible_observation_rejected(self):
        with self.assertRaisesRegex(ValueError,"EMPTY_REAL_SCORE_COHORT"):
            aggregate([])

    def test_wrong_score_type_rejected(self):
        for bad in ([True,2],[1.2,1],[-1,4],[21,2],None,[2,1,0]):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError,"INVALID_REAL_FT"):
                    score_over_275(bad)

    def test_invalid_illustrative_odds_rejected(self):
        for odds in (0,1,True,float("nan"),float("inf")):
            with self.subTest(odds=odds):
                with self.assertRaisesRegex(ValueError,"INVALID_REAL_FT"):
                    score_over_275([2,2],decimal=odds)

    def test_unavailable_real_dataset_is_fail_closed(self):
        def impossible():
            raise OSError("private data leaked should never be shown")
        r=audit(source_reader=impossible)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"REAL_GOAL_275_AUDIT_UNAVAILABLE")
        self.assertNotIn("private data",str(r))
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")


if __name__=="__main__":
    unittest.main()
