"""Research-only model price audit: exact quarter-line settlement and safeguards."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_price_audit import (audit_1x2, home_handicap_distribution,
                               neutral_decimal_price, hypothetical_profit)


class PriceAuditTests(unittest.TestCase):
    def test_liverpool_market_consensus_snapshot(self):
        market = [.2962518, .2573840, .4463642]
        result = audit_1x2([.35, .25, .4], market)
        self.assertAlmostEqual(result["market_reference_fair_1x2_not_quotes"][0], 3.37551, places=5)
        self.assertAlmostEqual(result["market_reference_home_plus_0_25_fair_not_quote"], 2.05041, places=5)
        self.assertAlmostEqual(result["market_reference_home_plus_0_5_fair_not_quote"], 1.80624, places=5)
        self.assertIsNone(result["recommendation"])
        self.assertFalse(result["official_lineup_incorporation_verified"])
        self.assertFalse(result["betting_positive_ev_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_quarter_win_loss_push_and_ev(self):
        p = [.30, .25, .45]
        plus = home_handicap_distribution(p, .25)
        self.assertAlmostEqual(plus["FULL_WIN"], .30)
        self.assertAlmostEqual(plus["HALF_WIN"], .25)
        self.assertAlmostEqual(plus["FULL_LOSS"], .45)
        self.assertAlmostEqual(neutral_decimal_price(plus), 1 + .45 / (.30 + .125))
        self.assertAlmostEqual(hypothetical_profit(plus, 1.90), .9 * (.30 + .125) - .45)
        zero = home_handicap_distribution(p, 0)
        self.assertAlmostEqual(zero["PUSH"], .25)
        minus = home_handicap_distribution(p, -.25)
        self.assertAlmostEqual(minus["HALF_LOSS"], .25)
        self.assertAlmostEqual(neutral_decimal_price(home_handicap_distribution(p, .5)),
                               1 + .45 / (.30 + .25))

    def test_invalid_input_and_unpriceable_lines_fail_closed(self):
        for bad in ([True, 0, 1], [.6, .6, .3], [float("nan"), 0, 1], [-1, 1, 1], "no"):
            with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                audit_1x2(bad, [.4, .3, .3])
        for line in (.75, 1, -1, float("nan"), True):
            with self.subTest(line=line), self.assertRaises(ValueError):
                home_handicap_distribution([.3, .3, .4], line)
        for odds in (0, True, 1.0, float("nan"), 1000):
            with self.subTest(odds=odds), self.assertRaises(ValueError):
                hypothetical_profit(home_handicap_distribution([.3, .3, .4], .25), odds)

    def test_zero_probability_never_returns_infinite_price(self):
        result = audit_1x2([0, 1, 0], [.5, .5, 0])
        self.assertIsNone(result["market_reference_fair_1x2_not_quotes"][2])
        self.assertIsNone(neutral_decimal_price(home_handicap_distribution([0, 0, 1], .25)))

    def test_no_false_production_authorization(self):
        v = audit_1x2([.3, .3, .4], [.33, .33, .34])
        self.assertTrue(v["market_probability_is_de_vigged_reference_not_licensed_execution"])
        self.assertFalse(v["quote_executable_verified"])
        self.assertFalse(v["independent_calibration_verified"])
        self.assertEqual(v["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
