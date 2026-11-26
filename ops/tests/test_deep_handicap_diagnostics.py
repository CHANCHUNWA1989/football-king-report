"""Deep line settlement, scenario conservation and fail-closed boundaries."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asian_handicap_research import probabilities, grade
from deep_handicap_diagnostics import analyze, _joint


class DeepHandicapTests(unittest.TestCase):
    def test_exact_deep_lines(self):
        for line, score, wanted in [
            (-1.5, 2, "FULL_WIN"), (-1.75, 2, "HALF_WIN"),
            (-2, 2, "PUSH"), (-2.25, 2, "HALF_LOSS"),
            (-2.5, 2, "FULL_LOSS"), (-3, 3, "PUSH"),
            (-3.25, 3, "HALF_LOSS"), (-5, 5, "PUSH")]:
            for side in ("HOME", "AWAY"):
                h, a = (score, 0) if side == "HOME" else (0, score)
                self.assertEqual(grade(h, a, side, line), wanted)

    def test_baseline_matches_existing_engine_and_mirror(self):
        for line in (-1.5, -1.75, -2, -2.25, -2.5, -3, -3.25, -4, -5):
            a = _joint(2.95, 1.17, "HOME", line)
            b = _joint(1.17, 2.95, "AWAY", line)
            existing = probabilities(2.95, 1.17, "HOME", line)
            for k, p in a["grades"].items():
                self.assertAlmostEqual(p, existing["outcome_probabilities"][k], places=6)
                self.assertAlmostEqual(p, b["grades"][k], places=10)
            self.assertAlmostEqual(sum(a["margin_buckets"].values()), 1)
            self.assertLessEqual(a["win_but_stake_loss_probability"], a["win_probability"])

    def test_stress_conservation_and_monotone_pace(self):
        for home, away in ((2.95, 1.17), (2.29, 1.04), (2.14, .86), (1, 2), (4, .5)):
            for line in (-1.5, -2.25, -3.5, -5):
                for side in ("HOME", "AWAY"):
                    full = _joint(home, away, side, line, 1)
                    slow = _joint(home, away, side, line, .65)
                    self.assertAlmostEqual(sum(slow["grades"].values()), 1)
                    self.assertAlmostEqual(sum(slow["margin_buckets"].values()), 1)
                    self.assertLessEqual(slow["grades"]["FULL_WIN"], full["grades"]["FULL_WIN"]+1e-9)

    def test_envelope_contains_baseline_and_never_qualifies(self):
        out = analyze(2.95, 1.17, "HOME", -2.25)
        self.assertEqual(out["stress_scenario_count"], 27)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertFalse(out["qualifies_for_betting"])
        self.assertFalse(out["positive_expected_value_verified"])
        p = out["baseline"]["grades"]["FULL_WIN"]
        self.assertLessEqual(out["full_win_envelope"]["min"], p)
        self.assertGreaterEqual(out["full_win_envelope"]["max"], p)

    def test_invalid_or_unsupported_stress_is_fail_closed(self):
        for h,a,side,line in [(True,1,"HOME",-2), (float("nan"),1,"HOME",-2),
                              (1,1,"HOME",-1.25), (1,1,"AWAY",2),
                              (1,1,"OTHER",-2), (1,1,"HOME",-2.1)]:
            with self.assertRaises(ValueError):
                analyze(h,a,side,line)
        out = analyze(5.5,.1,"HOME",-2)
        self.assertEqual(out["stress_status"], "INCOMPLETE_RATE_DOMAIN")
        self.assertNotIn("full_win_envelope",out)
        self.assertEqual(out["status"],"HOLD")
