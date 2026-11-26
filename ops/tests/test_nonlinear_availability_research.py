import copy
import math
import unittest

from ops.nonlinear_availability_research import evaluate


def scenario():
    return {"kind": "SYNTHETIC_SCENARIO_ONLY", "home_xg": 1.5, "away_xg": 1.0,
            "home": [{"starter_id": f"h{i}", "replacement_id": None,
                      "role": "GK" if i == 0 else "DEF" if i < 5 else "MID" if i < 9 else "FWD",
                      "starter": [0.7, 0.7], "replacement": None}
                     for i in range(11)],
            "away": [{"starter_id": f"a{i}", "replacement_id": None,
                      "role": "GK" if i == 0 else "DEF" if i < 5 else "MID" if i < 9 else "FWD",
                      "starter": [0.7, 0.7], "replacement": None}
                     for i in range(11)]}


def replace(s, side, i, strength):
    s[side][i].update(replacement_id=f"sub-{side}-{i}", replacement=strength)


class NonlinearAvailabilityTests(unittest.TestCase):
    def test_no_absence_is_identity(self):
        s = scenario()
        before = copy.deepcopy(s)
        r = evaluate(s)
        self.assertEqual(r["scenario_xg"], {"home": 1.5, "away": 1.0})
        self.assertEqual(s, before)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["real_player_effect_verified"])

    def test_attack_and_defense_channels(self):
        s = scenario()
        replace(s, "home", 9, [0.2, 0.7])
        r = evaluate(s)
        self.assertLess(r["scenario_xg"]["home"], 1.5)
        self.assertAlmostEqual(r["scenario_xg"]["away"], 1.0)
        s = scenario()
        replace(s, "home", 1, [0.7, 0.2])
        r = evaluate(s)
        self.assertAlmostEqual(r["scenario_xg"]["home"], 1.5)
        self.assertGreater(r["scenario_xg"]["away"], 1.0)

    def test_same_unit_positive_losses_compound(self):
        s = scenario()
        replace(s, "home", 1, [0.7, 0.2])
        single = evaluate(s)["scenario_xg"]["away"]
        replace(s, "home", 2, [0.7, 0.2])
        double = evaluate(s)["scenario_xg"]["away"]
        self.assertGreater(math.log(double), 2 * math.log(single))
        self.assertGreater(evaluate(s)["home_effect"]["defense_interaction"], 0)

    def test_better_replacement_and_equal_replacement(self):
        s = scenario()
        replace(s, "home", 9, [0.7, 0.7])
        self.assertAlmostEqual(evaluate(s)["scenario_xg"]["home"], 1.5)
        replace(s, "home", 9, [0.9, 0.7])
        self.assertGreater(evaluate(s)["scenario_xg"]["home"], 1.5)

    def test_missing_and_conflicting_inputs_rejected(self):
        for change in ("missing", "duplicate", "cross_team", "bool", "nan",
                       "partial_replacement", "real_claim", "bad_role", "unknown_field"):
            s = scenario()
            if change == "missing": s["home"].pop()
            elif change == "duplicate": s["home"][1]["starter_id"] = "h0"
            elif change == "cross_team": s["home"][1]["starter_id"] = "a1"
            elif change == "bool": s["home"][1]["starter"] = [True, .7]
            elif change == "nan": s["home"][1]["starter"] = [float("nan"), .7]
            elif change == "partial_replacement": s["home"][1]["replacement_id"] = "sub"
            elif change == "real_claim": s["kind"] = "AUTHENTICATED"
            elif change == "bad_role": s["home"][1]["role"] = "UNKNOWN"
            elif change == "unknown_field": s["home"][1]["actual_result"] = 1
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate(s)

    def test_side_symmetry(self):
        s = scenario()
        replace(s, "home", 1, [.3, .4])
        a = evaluate(s)["scenario_xg"]
        s["home"], s["away"] = s["away"], s["home"]
        s["home_xg"], s["away_xg"] = s["away_xg"], s["home_xg"]
        b = evaluate(s)["scenario_xg"]
        self.assertAlmostEqual(a["home"], b["away"])
        self.assertAlmostEqual(a["away"], b["home"])


if __name__ == "__main__":
    unittest.main()
