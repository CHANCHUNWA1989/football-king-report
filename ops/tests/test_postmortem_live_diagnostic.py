"""Synthetic regression tests only; no verified match or price evidence."""
import unittest
from ops.postmortem_live_diagnostic import (
    card_sensitivity, settlement_consistency, paired_diagnostic,
)
from ops.live_market_research import payout

class PostmortemRegression(unittest.TestCase):
    def case(self, **changes):
        x = dict(home_goals=2, away_goals=0, minute=60, home_remaining=.8,
                 away_remaining=.5, card_side="AWAY", official_card_side="AWAY",
                 independent_card_side="AWAY", official_source="synthetic-official",
                 independent_source="synthetic-independent",
                 disadvantaged_factor=.7, opponent_factor=1.3)
        x.update(changes)
        return card_sensitivity(**x)

    def test_card_away_direction_and_mass(self):
        r = self.case()
        a, b = r["comparison"].values()
        self.assertAlmostEqual(sum(a), 1)
        self.assertAlmostEqual(sum(b), 1)
        self.assertGreaterEqual(b[0], a[0])
        self.assertLessEqual(b[2], a[2])
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["source_authenticity_verified"])

    def test_home_card_direction(self):
        a, b = self.case(card_side="HOME", official_card_side="HOME",
                         independent_card_side="HOME")["comparison"].values()
        self.assertLessEqual(b[0], a[0])
        self.assertGreaterEqual(b[2], a[2])

    def test_conflicting_card(self):
        self.assertIsNone(self.case(independent_card_side="HOME")["comparison"])

    def test_same_source_label(self):
        self.assertIsNone(self.case(independent_source=" SYNTHETIC-OFFICIAL ")["comparison"])

    def test_invalid_rate_or_clock(self):
        for changes in ({"home_remaining": float("nan")}, {"minute": -1},
                        {"disadvantaged_factor": 1.1}, {"home_goals": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.case(**changes)

    def test_terminal_clock(self):
        self.assertIsNone(self.case(minute=90)["comparison"])

    def test_cross_engine_grid(self):
        for h in range(8):
            for a in range(8):
                for side in ("HOME", "AWAY"):
                    for units in range(-20, 21):
                        settlement_consistency(h, a, side, units/4, 1.91)

    def test_quarter_line_and_large_defeat(self):
        self.assertEqual(settlement_consistency(1, 1, "HOME", -.25, 2), ("HALF_LOSS", -.5))
        self.assertEqual(settlement_consistency(1, 1, "AWAY", .25, 2), ("HALF_WIN", .5))
        self.assertEqual(settlement_consistency(4, 0, "AWAY", .25, 2), ("FULL_LOSS", -1))
        self.assertEqual(payout(dict(kind="totals", side="over", line=3, odds=2), 3, 0), 0)

    def row(self, **changes):
        r = dict(fixture_id="synthetic-1", training_cutoff="2026-01-01T00:00:00Z",
                 prediction_time="2026-01-02T00:00:00Z", result_time="2026-01-03T00:00:00Z",
                 baseline=[.4,.3,.3], challenger=[.6,.2,.2], outcome=0)
        r.update(changes)
        return r

    def test_paired_brier_only_diagnostic(self):
        r = paired_diagnostic([self.row()])
        self.assertAlmostEqual(r["mean_paired_brier_delta"], -.30)
        self.assertFalse(r["out_of_sample_proven"])
        self.assertFalse(r["promotion_allowed"])
        self.assertIsNone(r["confidence_interval"])

    def test_leakage_and_naive_timestamp(self):
        for changes in ({"training_cutoff":"2026-01-02T00:00:00Z"},
                        {"result_time":"2026-01-01T00:00:00Z"},
                        {"prediction_time":"2026-01-02T00:00:00"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                paired_diagnostic([self.row(**changes)])

    def test_duplicate_and_bad_probability(self):
        with self.assertRaises(ValueError):
            paired_diagnostic([self.row(), self.row()])
        with self.assertRaises(ValueError):
            paired_diagnostic([self.row(challenger=[.8,.3,.3])])

    def test_empty_cohort_hold(self):
        r = paired_diagnostic([])
        self.assertEqual(r["status"], "HOLD")
        self.assertIsNone(r["mean_paired_brier_delta"])

if __name__ == "__main__":
    unittest.main()
