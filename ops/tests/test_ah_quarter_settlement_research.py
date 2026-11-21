"""Synthetic research-only settlement regression. Not actual match results."""
import unittest
from ops.ah_quarter_settlement_research import settle


class AsianHandicapQuarterSettlementTests(unittest.TestCase):
    def test_all_five_grades(self):
        cases = [
            ((2, 0, "home", "-0.75", "2", "10"), "FULL_WIN", "10"),
            ((1, 0, "home", "-0.75", "2", "10"), "HALF_WIN", "5"),
            ((1, 0, "home", "-1", "2", "10"), "PUSH", "0"),
            ((0, 1, "home", "+0.75", "2", "10"), "HALF_LOSS", "-5"),
            ((0, 2, "home", "+0.75", "2", "10"), "FULL_LOSS", "-10"),
        ]
        for args, grade, net in cases:
            with self.subTest(args=args):
                result = settle(*args)
                self.assertEqual(result["grade"], grade)
                self.assertEqual(float(result["net_profit"]), float(net))
                self.assertEqual(result["production_recommendations"], "DISABLED")
                self.assertFalse(result["positive_ev_verified"])

    def test_south_hobart_plus_two_point_two_five_synthetic(self):
        self.assertEqual(settle(2, 0, "away", "+2.25", "1.91", "10")["grade"], "HALF_WIN")
        self.assertEqual(settle(3, 0, "away", "+2.25", "1.91", "10")["grade"], "FULL_LOSS")

    def test_wollongong_plus_point_seven_five_synthetic(self):
        result = settle(1, 0, "away", "+0.75", "2", "10")
        self.assertEqual(result["grade"], "HALF_LOSS")
        self.assertEqual(float(result["net_profit"]), -5)

    def test_negative_quarter_line_split(self):
        self.assertEqual(settle(1, 0, "home", "-1.25", "2", "10")["grade"], "HALF_LOSS")
        self.assertEqual(settle(2, 0, "home", "-1.25", "2", "10")["grade"], "FULL_WIN")

    def test_invalid_inputs_fail_closed(self):
        for args in [(True, 0, "home", "0", "2", "1"),
                     (0, 0, "home", "+0.3", "2", "1"),
                     (0, 0, "home", "0", "NaN", "1"),
                     (0, 0, "home", "0", "1", "1"),
                     (0, 0, "home", "0", "2", "-1")]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                settle(*args)

    def test_exhaustive_quarter_tick_oracle(self):
        # Independent integer-tick oracle: compare all 4-tick quarter lines
        # and both sides across synthetic scores, including negative spreads.
        from decimal import Decimal
        for home in range(5):
            for away in range(5):
                for side in ("home", "away"):
                    margin = home-away if side == "home" else away-home
                    for ticks in range(-16, 17):
                        with self.subTest(home=home, away=away, side=side, ticks=ticks):
                            # A quarter handicap has two neighboring half-goal legs.
                            lower_ticks = (ticks // 2) * 2
                            upper_ticks = lower_ticks if ticks % 2 == 0 else lower_ticks + 2
                            leg_ticks = (lower_ticks, upper_ticks)
                            net = Decimal("0")
                            for leg in leg_ticks:
                                adjusted_ticks = 4 * margin + leg
                                net += (Decimal("0.5") if adjusted_ticks > 0 else
                                        Decimal("-0.5") if adjusted_ticks < 0 else Decimal("0"))
                            grade = {Decimal("1"): "FULL_WIN", Decimal("0.5"): "HALF_WIN",
                                     Decimal("0"): "PUSH", Decimal("-0.5"): "HALF_LOSS",
                                     Decimal("-1"): "FULL_LOSS"}[net]
                            result = settle(home, away, side, str(Decimal(ticks)/4), "2", "1")
                            self.assertEqual(result["grade"], grade)
                            self.assertEqual(Decimal(result["net_profit"]), net)
                            self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
