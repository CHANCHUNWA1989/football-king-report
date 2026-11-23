"""Research-only joint-outcome Kelly portfolio drawdown tests.

No live odds, bankroll, execution or calibrated model data is used.
Synthetic exposures are user-supplied for maths stress testing only.
"""
import math
import unittest

from ops.portfolio_risk_shadow import assess, evaluate_hypothetical


def correlated():
    return [
        {"probability": .55, "returns": [.9, .9]},
        {"probability": .45, "returns": [-1, -1]},
    ]


class PortfolioShadowTests(unittest.TestCase):
    def test_correlated_same_fixture_loss_and_compounding_drawdown(self):
        case = evaluate_hypothetical(correlated(), [.1, .1], [[1, 1, 1], [0, 1, 1]])
        self.assertEqual(case["status"], "HYPOTHETICAL_ONLY")
        self.assertEqual(case["scenario_count"], 2)
        self.assertAlmostEqual(case["expected_net_fraction"], .009)
        self.assertAlmostEqual(case["worst_round_net_fraction"], -.2)
        self.assertAlmostEqual(case["worst_stress_max_drawdown"], .488)
        self.assertAlmostEqual(case["worst_stress_terminal_equity"], .512)
        self.assertAlmostEqual(case["expected_log_growth"],
                               .55 * math.log1p(.18) + .45 * math.log1p(-.2))
        self.assertFalse(case["bet_eligible"])
        self.assertIsNone(case["suggested_stake"])
        self.assertEqual(case["production_recommendations"], "DISABLED")

    def test_joint_scenarios_are_not_independent_bet_assumptions(self):
        # Same marginal win probabilities; outcomes win/lose together versus
        # independent pseudo-world. The arithmetic EV is identical but
        # positive correlation causes worse expected portfolio log growth.
        independent = [
            {"probability": .3025, "returns": [.9, .9]},
            {"probability": .2475, "returns": [.9, -1]},
            {"probability": .2475, "returns": [-1, .9]},
            {"probability": .2025, "returns": [-1, -1]},
        ]
        together = evaluate_hypothetical(correlated(), [.1, .1])
        separate = evaluate_hypothetical(independent, [.1, .1])
        self.assertAlmostEqual(together["expected_net_fraction"],
                               separate["expected_net_fraction"])
        self.assertLess(together["expected_log_growth"],
                        separate["expected_log_growth"])
        self.assertIsNone(together["worst_stress_max_drawdown"])
        self.assertFalse(together["independent_joint_distribution_verified"])

    def test_stress_paths_do_not_fabricate_historical_drawdown(self):
        result = evaluate_hypothetical(
            [{"probability": .5, "returns": [.5]}, {"probability": .5, "returns": [-1]}],
            [.1], stress_paths=[])
        self.assertIsNone(result["worst_stress_max_drawdown"])
        self.assertIsNone(result["worst_stress_terminal_equity"])
        self.assertFalse(result["observed_drawdown_verified"])

    def test_real_case_without_optin_must_hold(self):
        result = assess(correlated(), [.1, .1], [[1, 1, 1]])
        self.assertEqual(result["status"], "HOLD")
        self.assertIsNone(result["expected_net_fraction"])
        self.assertIsNone(result["worst_stress_max_drawdown"])
        self.assertFalse(result["bet_eligible"])
        self.assertIsNone(result["suggested_stake"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_hypothetical_optin_still_never_offers_stakes(self):
        result = assess(correlated(), [.1, .1], [[1, 1, 1]], hypothetical=True)
        self.assertEqual(result["status"], "HYPOTHETICAL_ONLY")
        self.assertFalse(result["bet_eligible"])
        self.assertIsNone(result["suggested_stake"])
        self.assertFalse(result["independent_joint_distribution_verified"])
        self.assertFalse(result["executable_quote_verified"])

    def test_malformed_inputs_rejected(self):
        bad = [
            ([{"probability": .5, "returns": [.9, .9]}], [.1, .1], []),  # non-normalized
            ([{"probability": True, "returns": [.9]}], [.1], []),
            ([{"probability": 1, "returns": [float("nan")]}], [.1], []),
            ([{"probability": 1, "returns": [float("inf")]}], [.1], []),
            ([{"probability": 1, "returns": [True]}], [.1], []),
            ([{"probability": 1, "returns": [-1]}], [-.1], []),
            ([{"probability": 1, "returns": [-1]}], [True], []),
            ([{"probability": 1, "returns": [-1]}], [1.1], []),
            ([{"probability": 1, "returns": [-1]}], [0], []),  # no exposure
            ([{"probability": 1, "returns": [-1]}], [1], []),  # certain ruin
            ([{"probability": 1, "returns": [100]}], [.1], []),
            ([{"probability": 1, "returns": [-1]}], [.1], [[1]]),  # unknown state
            ([{"probability": 1, "returns": [-1]}], [.1], [[True]]),
            ([{"probability": 1, "returns": [-1]}], [.1], [[0] * 129]),
            ([{"probability": 1, "returns": [-1], "source": "certified"}], [.1], []),
            ([{"probability": 1, "returns": [-1, 0]}], [.1], []),
        ]
        for states, fractions, paths in bad:
            with self.subTest(case=(states, fractions, paths)):
                with self.assertRaises(ValueError):
                    evaluate_hypothetical(states, fractions, paths)

    def test_bounded_joint_scenarios_and_stress_paths(self):
        scenarios = [
            {"probability": 1.0 / 257, "returns": [-.1]} for _ in range(257)
        ]
        with self.assertRaisesRegex(ValueError, "TOO_MANY_SCENARIOS"):
            evaluate_hypothetical(scenarios, [.1], [])
        with self.assertRaisesRegex(ValueError, "TOO_MANY_STRESS_PATHS"):
            evaluate_hypothetical([{"probability": 1, "returns": [-.1]}],
                                  [.1], [[0]] * 65)

    def test_early_hold_does_not_trust_bogus_inputs(self):
        self.assertEqual(assess(hypothetical=False)["status"], "HOLD")
        self.assertEqual(assess([{"probability": "fake"}], "fake")["status"], "HOLD")

    def test_all_profitable_paths_report_actual_terminal_equity(self):
        # Previously initialized worst_terminal=1.0 and incorrectly returned
        # 1.0 even when EVERY synthetic stress path finished above 1.0.
        win_only = [{"probability": 1.0, "returns": [.2]}]
        case = evaluate_hypothetical(win_only, [.5], [[0, 0], [0]])
        self.assertAlmostEqual(case["worst_stress_terminal_equity"], 1.10)
        self.assertAlmostEqual(case["worst_stress_max_drawdown"], 0.0)
        self.assertFalse(case["observed_drawdown_verified"])

    def test_profit_then_loss_tracks_running_peak_and_terminal_separately(self):
        # +10%, then -5% net => terminal 1.045; 5% peak-to-trough drawdown.
        paired = [
            {"probability": .5, "returns": [.2]},
            {"probability": .5, "returns": [-.1]},
        ]
        case = evaluate_hypothetical(paired, [.5], [[0, 1]])
        self.assertAlmostEqual(case["worst_stress_terminal_equity"], 1.045)
        self.assertAlmostEqual(case["worst_stress_max_drawdown"], .05)


if __name__ == "__main__":
    unittest.main()
