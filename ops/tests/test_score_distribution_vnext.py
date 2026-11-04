"""Synthetic cross-market invariants for the unified research score matrix."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_handicap_research import grade as previous_ah_grade
from shadow_forecast import poisson_1x2 as old_poisson_1x2
from score_distribution_vnext import (
    GRADE_NAMES, audit_report, build_report, grade_score, market_distribution,
    one_x_two, score_matrix, validate_matrix,
)


def requests():
    return [
        {"market": "h2h", "side": "HOME", "line": None},
        {"market": "h2h", "side": "DRAW", "line": None},
        {"market": "h2h", "side": "AWAY", "line": None},
        {"market": "asian_handicap", "side": "HOME", "line": -0.75},
        {"market": "totals", "side": "OVER", "line": 2.25},
    ]


class UnifiedScoreMarketsTests(unittest.TestCase):
    def test_positive_matrix_and_total_probability(self):
        g = score_matrix(1.65, 1.2)
        self.assertAlmostEqual(sum(map(sum, g)), 1.0, places=10)
        self.assertGreater(len(g), 8)
        self.assertTrue(all(math.isfinite(p) and p >= 0 for row in g for p in row))

    def test_1x2_sums_exactly_from_single_matrix(self):
        g = score_matrix(1.65, 1.2)
        p = one_x_two(g)
        self.assertAlmostEqual(sum(p.values()), 1, places=10)
        self.assertEqual(set(p), {"HOME", "DRAW", "AWAY"})
        self.assertGreater(p["HOME"], p["AWAY"])

    def test_equal_rates_swap_win_probabilities(self):
        p = one_x_two(score_matrix(1.55, 1.55))
        self.assertAlmostEqual(p["HOME"], p["AWAY"], places=12)

    def test_swap_teams_swaps_home_away_probabilities(self):
        a = one_x_two(score_matrix(1.8, 0.9))
        b = one_x_two(score_matrix(0.9, 1.8))
        self.assertAlmostEqual(a["HOME"], b["AWAY"], places=11)
        self.assertAlmostEqual(a["DRAW"], b["DRAW"], places=11)

    def test_rho_zero_matches_existing_poisson_reasonably(self):
        p = one_x_two(score_matrix(1.3, 1.2))
        original = old_poisson_1x2(1.3, 1.2)
        for actual, expected in zip((p["HOME"], p["DRAW"], p["AWAY"]), original):
            self.assertAlmostEqual(actual, expected, delta=3e-7)

    def test_fixed_dixon_coles_changes_low_score_without_fitting(self):
        baseline = score_matrix(1.3, 1.2)
        changed = score_matrix(1.3, 1.2, rho=-.05)
        self.assertGreater(changed[0][0], baseline[0][0])
        self.assertAlmostEqual(sum(map(sum, changed)), 1, places=10)

    def test_dc_nonpositive_tau_fails_closed(self):
        r = audit_report(5.5, 5.5, requests(), rho=.10)
        self.assertEqual(r["reason"], "NONPOSITIVE_DIXON_COLES_FACTOR")

    def test_bad_rate_or_rho_never_accepted(self):
        for rate in (True, -1, 0, float("nan"), float("inf"), 10, "1.5"):
            with self.subTest(rate=rate):
                self.assertEqual(audit_report(rate, 1.2, requests())["status"], "HOLD")
        self.assertEqual(audit_report(1, 1, requests(), rho="0")["status"], "HOLD")

    def test_tail_tolerance_must_be_bounded(self):
        for value in (1, 0, -1, float("nan"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    score_matrix(1.0, 1.0, tail_tolerance=value)

    def test_extreme_score_tail_is_present(self):
        g = score_matrix(5.5, 5.5, tail_tolerance=1e-12)
        self.assertGreater(g[6][0], 0)
        self.assertGreater(g[0][6], 0)
        self.assertGreater(len(g), 14)
        self.assertAlmostEqual(sum(map(sum, g)), 1, places=10)

    def test_legacy_asian_grades_agree_for_regulation_results(self):
        for home, away in ((0, 0), (1, 0), (0, 1), (3, 2), (6, 0)):
            for side in ("HOME", "AWAY"):
                for line in (-2.5, -.75, -.5, -.25, 0, .25, .75, 1, 2.5):
                    with self.subTest(home=home, away=away, side=side, line=line):
                        self.assertEqual(
                            grade_score(home, away, market="asian_handicap", side=side, line=line),
                            previous_ah_grade(home, away, side, line),
                        )

    def test_quarter_handicap_full_half_push_and_loss(self):
        cases = [
            (1, 1, "HOME", -.25, "HALF_LOSS"),
            (1, 1, "HOME", .25, "HALF_WIN"),
            (1, 0, "HOME", -.75, "HALF_WIN"),
            (1, 0, "HOME", -1.0, "PUSH"),
            (0, 1, "HOME", -.5, "FULL_LOSS"),
            (2, 0, "HOME", -1.5, "FULL_WIN"),
            (0, 0, "AWAY", 0, "PUSH"),
        ]
        for h, a, side, line, expected in cases:
            with self.subTest(h=h, a=a, side=side, line=line):
                self.assertEqual(grade_score(h, a, market="asian_handicap", side=side, line=line),
                                 expected)

    def test_quarter_totals_full_half_push_and_loss(self):
        cases = [
            (1, 1, "OVER", 2.25, "HALF_LOSS"),
            (1, 1, "UNDER", 2.25, "HALF_WIN"),
            (2, 1, "OVER", 2.75, "HALF_WIN"),
            (2, 1, "UNDER", 2.75, "HALF_LOSS"),
            (2, 1, "OVER", 2.5, "FULL_WIN"),
            (2, 1, "UNDER", 2.5, "FULL_LOSS"),
            (0, 0, "OVER", 0, "PUSH"),
            (0, 0, "UNDER", 0, "PUSH"),
        ]
        for h, a, side, line, expected in cases:
            with self.subTest(h=h, a=a, side=side, line=line):
                self.assertEqual(grade_score(h, a, market="totals", side=side, line=line),
                                 expected)

    def test_opposing_handicap_grades_are_complements(self):
        opposite = {"FULL_WIN": "FULL_LOSS", "HALF_WIN": "HALF_LOSS",
                    "PUSH": "PUSH", "HALF_LOSS": "HALF_WIN", "FULL_LOSS": "FULL_WIN"}
        grid = score_matrix(1.6, 1.1)
        home = market_distribution(grid, market="asian_handicap", side="HOME", line=-.75)
        away = market_distribution(grid, market="asian_handicap", side="AWAY", line=.75)
        for category in GRADE_NAMES:
            self.assertAlmostEqual(home["outcome_probabilities"][category],
                                   away["outcome_probabilities"][opposite[category]], places=11)

    def test_over_under_probabilities_are_complements(self):
        opposite = {"FULL_WIN": "FULL_LOSS", "HALF_WIN": "HALF_LOSS",
                    "PUSH": "PUSH", "HALF_LOSS": "HALF_WIN", "FULL_LOSS": "FULL_WIN"}
        grid = score_matrix(1.6, 1.1)
        over = market_distribution(grid, market="totals", side="OVER", line=2.25)
        under = market_distribution(grid, market="totals", side="UNDER", line=2.25)
        for category in GRADE_NAMES:
            self.assertAlmostEqual(over["outcome_probabilities"][category],
                                   under["outcome_probabilities"][opposite[category]], places=11)

    def test_all_market_outcomes_sum_to_one(self):
        g = score_matrix(1.6, 1.1)
        for m, s, line in (("asian_handicap", "HOME", -.75),
                            ("asian_handicap", "AWAY", .25),
                            ("totals", "OVER", 2.25), ("totals", "UNDER", 3.0)):
            with self.subTest(m=m, s=s, line=line):
                d = market_distribution(g, market=m, side=s, line=line)
                self.assertAlmostEqual(sum(d["outcome_probabilities"].values()), 1, places=10)

    def test_three_way_and_h2h_market_use_same_probabilities(self):
        grid = score_matrix(1.4, 1.2)
        total = one_x_two(grid)
        for side in ("HOME", "DRAW", "AWAY"):
            info = market_distribution(grid, market="h2h", side=side)
            self.assertEqual(info["outcome_probabilities"], total)
            self.assertEqual(info["selected_probability"], total[side])

    def test_high_totals_line_accepts_legal_quarter(self):
        self.assertEqual(grade_score(10, 2, market="totals",
                                     side="OVER", line=11.75), "HALF_WIN")

    def test_non_quarter_line_and_nan_are_rejected(self):
        for line in (.3, float("nan"), float("inf"), True, "2.33"):
            with self.subTest(line=line):
                self.assertEqual(audit_report(1.3, 1.1, [
                    {"market": "totals", "side": "OVER", "line": line}
                ])["status"], "HOLD")

    def test_unsupported_market_and_invalid_market_side_hold(self):
        for market, side, line in (("corners", "OVER", 2.5),
                                   ("totals", "HOME", 2.5),
                                   ("asian_handicap", "DRAW", 0),
                                   ("h2h", "HOME", 0)):
            with self.subTest(market=market):
                self.assertEqual(audit_report(1.3, 1.1, [
                    {"market": market, "side": side, "line": line}
                ])["status"], "HOLD")

    def test_invalid_score_and_extra_time_data_rejected(self):
        for home, away in ((True, 0), (-1, 0), (1.2, 0), (81, 0)):
            with self.subTest(home=home, away=away):
                with self.assertRaises(ValueError):
                    grade_score(home, away, market="h2h", side="HOME")

    def test_matrix_validation_rejects_bad_values_and_shape(self):
        bads = [
            [[.5, .4]], [[1.01]], [[True]], [[float("nan")]],
            [[.5, .5], [.1]], [], [[], []], "not a matrix"
        ]
        for bad in bads:
            with self.subTest(matrix=bad):
                with self.assertRaises(ValueError):
                    validate_matrix(bad)

    def test_full_report_has_one_matrix_and_explicit_no_ev(self):
        r = build_report(1.5, 1.2, requests())
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["full_time_scope"], "REGULATION_90_MINUTES_INCLUDING_STOPPAGE")
        self.assertFalse(r["remaining_only_in_play_markets_supported"])
        self.assertFalse(r["model_calibrated"])
        self.assertFalse(r["source_authenticated"])
        self.assertFalse(r["input_point_in_time_verified"])
        self.assertFalse(r["bookmaker_quote_authenticated"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["qualifies_for_betting"])
        self.assertFalse(r["model_scoring_eligible"])
        self.assertEqual(len(r["score_matrix_sha256"]), 64)
        self.assertEqual(len(r["markets"]), 5)
        for item in r["markets"][:3]:
            self.assertEqual(item["outcome_probabilities"], r["probabilities_1x2"])

    def test_deterministic_matrix_fingerprint(self):
        first = build_report(1.3, 1.5, requests())
        second = build_report(1.3, 1.5, list(reversed(requests())))
        self.assertEqual(first["score_matrix_sha256"], second["score_matrix_sha256"])
        self.assertEqual(first["probabilities_1x2"], second["probabilities_1x2"])

    def test_duplicate_market_does_not_silently_pass(self):
        request = requests()[0]
        self.assertEqual(audit_report(1, 1, [request, dict(request)])["reason"],
                         "DUPLICATE_MARKET_REQUEST")

    def test_invalid_market_request_fails_whole_batch(self):
        requests_bad = requests() + [{"market": "totals", "side": "OVER",
                                     "line": 2.5, "decimal_odds": 1.9}]
        report = audit_report(1.5, 1.0, requests_bad)
        self.assertEqual(report["status"], "HOLD")
        self.assertNotIn("markets", report)
        self.assertFalse(report["positive_ev_verified"])

    def test_missing_and_oversized_market_request_holds(self):
        self.assertEqual(audit_report(1, 1, [])["status"], "HOLD")
        self.assertEqual(audit_report(1, 1, [{}] * 25)["status"], "HOLD")

    def test_market_line_outside_supported_handicap_range_holds(self):
        self.assertEqual(audit_report(1, 1, [
            {"market": "asian_handicap", "side": "HOME", "line": -7.0}
        ])["status"], "HOLD")

    def test_production_status_is_disabled_on_failure_too(self):
        r = audit_report("unverified", 1.3, requests())
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["positive_ev_verified"])


if __name__ == "__main__":
    unittest.main()
