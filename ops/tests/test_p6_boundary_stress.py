"""P6 deterministic offline boundary stress; not genuine football evidence."""
import math
import unittest

from ops.v5_live_xg_comeback import distribution
from ops.nonlinear_availability_research import evaluate
from ops.tests.test_nonlinear_availability_research import scenario, replace
from ops.tests.test_chat_postmatch_research_audit import pick
from ops.chat_postmatch_research_audit import audit


class P6BoundaryStress(unittest.TestCase):
    def test_144_score_rate_combinations_mass_symmetry_and_comeback(self):
        n = 0
        for h in range(3):
            for a in range(3):
                for rh in (0., .01, 2., 8.):
                    for ra in (0., .01, 2., 8.):
                        d = distribution(h, a, rh, ra)
                        mirror = distribution(a, h, ra, rh)
                        for vector in (d["1x2"], d["final_total_p"].values(),
                                       d["final_margin_p"].values()):
                            self.assertTrue(all(math.isfinite(x) and 0 <= x <= 1
                                                for x in vector))
                            self.assertAlmostEqual(sum(vector), 1., places=10)
                        for x, y in zip(d["1x2"], reversed(mirror["1x2"])):
                            self.assertAlmostEqual(x, y, places=10)
                        if h == a:
                            self.assertIsNone(d["trailing_team_final_win_p"])
                        else:
                            trailing = 0 if h < a else 2
                            self.assertEqual(d["trailing_team_final_win_p"], d["1x2"][trailing])
                            self.assertEqual(d["trailing_team_final_draw_p"], d["1x2"][1])
                        if rh == ra == 0:
                            winner = 0 if h > a else 1 if h == a else 2
                            self.assertEqual(d["1x2"][winner], 1.)
                        n += 1
        self.assertEqual(n, 144)

    def test_25_replacement_scenarios_bounded_and_monotone(self):
        n = 0
        for count in range(5):
            previous = None
            for rating in (0., .25, .5, .75, 1.):
                s = scenario()
                for i in range(1, count + 1):
                    replace(s, "home", i, [.7, rating])
                d = evaluate(s)
                self.assertEqual(d["production_recommendations"], "DISABLED")
                self.assertEqual(d["certified_forward_samples"], 0)
                self.assertFalse(d["real_player_effect_verified"])
                self.assertLessEqual(abs(d["home_effect"]["defense_log_loss"]), .7)
                away = d["scenario_xg"]["away"]
                self.assertTrue(math.isfinite(away) and away > 0)
                if previous is not None:
                    self.assertLessEqual(away, previous + 1e-12)
                previous = away
                n += 1
        self.assertEqual(n, 25)

    def test_27_1x2_results_and_zero_remaining_goals_agree(self):
        for h in range(3):
            for a in range(3):
                d = distribution(h, a, 0., 0.)["1x2"]
                for i, side in enumerate(("HOME", "DRAW", "AWAY")):
                    r = audit([pick("synthetic", "1x2", side, None, [h, a])])
                    self.assertEqual(r["cases"][0]["grade_if_reported_score_is_correct"],
                                     "FULL_WIN" if d[i] == 1. else "FULL_LOSS")
                    self.assertEqual(r["formal_bet_count"], 0)
                    self.assertIsNone(r["roi"])
                    self.assertIsNone(r["ev"])


if __name__ == "__main__":
    unittest.main()
