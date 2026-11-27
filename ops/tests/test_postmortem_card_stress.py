"""Offline red-card scenario stress. No match or training evidence."""
import itertools
import math
import unittest
from ops.postmortem_live_diagnostic import card_sensitivity


def scenario(h, a, rh, ra, minute, side, down, up):
    return card_sensitivity(
        home_goals=h, away_goals=a, minute=minute,
        home_remaining=rh, away_remaining=ra, card_side=side,
        official_card_side=side, independent_card_side=side,
        official_source="synthetic-a", independent_source="synthetic-b",
        disadvantaged_factor=down, opponent_factor=up)


class CardStress(unittest.TestCase):
    def test_actual_adjusted_rate_not_false_overflow(self):
        r = scenario(0, 2, 8, 1, 45, "HOME", .5, 2)
        self.assertIsNotNone(r["comparison"])
        self.assertEqual(r["status"], "HOLD")
        r = scenario(0, 2, 1, 8, 45, "HOME", .5, 2)
        self.assertEqual(r["reason"], "ADJUSTED_RATE_OUT_OF_RANGE")
        self.assertIsNone(r["comparison"])

    def test_monotonic_grid(self):
        count = 0
        for (h,a),(rh,ra),minute,side,(down,up) in itertools.product(
                [(0,0),(0,2),(2,0),(1,1),(4,0),(0,4)],
                [(0,0),(.1,.1),(.8,.5),(3,1),(1,3),(4,4)],
                [1,45,89], ["HOME","AWAY"], [(1,1),(.7,1.3),(0,2)]):
            with self.subTest(h=h,a=a,rh=rh,ra=ra,minute=minute,side=side,down=down,up=up):
                r = scenario(h,a,rh,ra,minute,side,down,up)
                before, after = r["comparison"].values()
                for p in (before, after):
                    self.assertTrue(all(math.isfinite(v) and 0 <= v <= 1 for v in p))
                    self.assertAlmostEqual(sum(p),1,places=12)
                if side == "HOME":
                    self.assertLessEqual(after[0], before[0]+1e-12)
                    self.assertGreaterEqual(after[2], before[2]-1e-12)
                else:
                    self.assertGreaterEqual(after[0], before[0]-1e-12)
                    self.assertLessEqual(after[2], before[2]+1e-12)
                if down == up == 1:
                    self.assertEqual(before,after)
                self.assertFalse(r["promotion_allowed"])
                self.assertFalse(r["source_authenticity_verified"])
                self.assertEqual(r["production_recommendations"], "DISABLED")
                count += 1
        self.assertEqual(count,648)

    def test_home_away_swap_symmetry(self):
        x = scenario(2,0,.8,.5,60,"AWAY",.7,1.3)["comparison"]
        y = scenario(0,2,.5,.8,60,"HOME",.7,1.3)["comparison"]
        for key in x:
            for a,b in zip(x[key],reversed(y[key])):
                self.assertAlmostEqual(a,b,places=12)

    def test_zero_rates_and_terminal_clock(self):
        r = scenario(0,2,0,0,89,"HOME",.7,1.3)
        self.assertEqual(r["comparison"]["same_score_card"],[0.,0.,1.])
        r = scenario(0,2,0,0,90,"HOME",.7,1.3)
        self.assertEqual(r["reason"],"END_OF_REGULATION")
        self.assertIsNone(r["comparison"])


if __name__ == "__main__":
    unittest.main()
