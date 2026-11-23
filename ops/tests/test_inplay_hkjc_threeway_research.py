"""Offline synthetic examples only. These are NOT live source or wagering tests."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_hkjc_threeway_research import evaluate, _project
from inplay_remaining_goal_baseline import evaluate as baseline_evaluate


def sample():
    return {
        "fixture": {"fixture_id": "synthetic-fixture-1", "home_id": "home1",
                    "away_id": "away1", "kickoff_utc": "2026-11-23T05:00:00Z"},
        "prematch": {"home_goals_per_90": 0.9, "away_goals_per_90": 2.1,
                     "generated_utc": "2026-11-23T04:20:00Z",
                     "origin": "UNATTESTED_RESEARCH_ASSUMPTION"},
        "state": {"fixture_id": "synthetic-fixture-1",
                  "observed_utc": "2026-11-23T05:52:00Z",
                  "as_of_utc": "2026-11-23T05:52:15Z",
                  "match_status": "HALF_TIME", "elapsed_regulation_minutes": 45,
                  "home_goals": 0, "away_goals": 0,
                  "home_red_cards": 0, "away_red_cards": 0},
    }


class InplayHkjcThreeWayTests(unittest.TestCase):
    def test_research_only_and_threeway_normalization(self):
        result = evaluate(sample(), home_handicap=1)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["handicap_contract"], "HKJC_THREE_WAY_NOT_ASIAN_HANDICAP")
        self.assertEqual(len(result["scenarios"]), 3)
        for r in result["scenarios"]:
            self.assertAlmostEqual(sum(r[k] for k in
                ("home_handicap_win", "handicap_draw", "away_handicap_win")), 1, places=6)
            self.assertGreater(r["handicap_draw"], 0)
        for k in ("model_scoring_eligible", "probabilities_calibrated", "positive_ev_verified",
                  "event_source_authenticated", "live_odds_verified", "betting_eligible"):
            self.assertFalse(result[k])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIsNone(result["recommendation"])
        self.assertIsNone(result["stakes"])

    def test_hkjc_plus_one_away_by_one_is_draw_not_push(self):
        self.assertEqual(_project(0, 1, 0, 0, 1), [0, 1, 0])
        self.assertEqual(_project(0, 2, 0, 0, 1), [0, 0, 1])
        self.assertEqual(_project(1, 1, 0, 0, 1), [1, 0, 0])

    def test_zero_handicap_equals_original_1x2(self):
        case = sample()
        result = evaluate(case, home_handicap=0)
        base = baseline_evaluate(case)
        for tri, old in zip(result["scenarios"], base["scenarios"]):
            for k1, k2 in (("home_handicap_win", "home_win"),
                           ("handicap_draw", "draw"), ("away_handicap_win", "away_win")):
                self.assertAlmostEqual(tri[k1], old[k2], places=6)

    def test_plus_two_exact_handicap_draw(self):
        self.assertEqual(_project(0, 2, 0, 0, 2), [0, 1, 0])
        self.assertEqual(_project(0, 3, 0, 0, 2), [0, 0, 1])

    def test_negative_home_handicap(self):
        self.assertEqual(_project(1, 0, 0, 0, -1), [0, 1, 0])
        self.assertEqual(_project(2, 0, 0, 0, -1), [1, 0, 0])

    def test_no_input_mutation(self):
        case = sample()
        backup = copy.deepcopy(case)
        evaluate(case)
        self.assertEqual(case, backup)

    def test_rejects_bool_noninteger_and_large_handicap(self):
        for x in (True, 0.25, -0.75, 4, -4, None, "1"):
            self.assertEqual(evaluate(sample(), x)["reason"], "INVALID_THREEWAY_HANDICAP")

    def test_red_card_not_assumed_away(self):
        case = sample()
        case["state"]["away_red_cards"] = 1
        result = evaluate(case)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["scenarios"], [])

    def test_missing_red_card_not_inferred_zero(self):
        case = sample()
        del case["state"]["home_red_cards"]
        self.assertEqual(evaluate(case)["status"], "HOLD")

    def test_stale_or_inconsistent_snapshot_fails_closed(self):
        case = sample()
        case["state"]["as_of_utc"] = "2026-11-23T06:00:00Z"
        self.assertEqual(evaluate(case)["status"], "HOLD")
        case = sample()
        case["state"]["elapsed_regulation_minutes"] = 7
        self.assertEqual(evaluate(case)["status"], "HOLD")

    def test_no_postmatch_or_result_lookahead(self):
        case = sample()
        case["state"]["match_status"] = "FINISHED"
        case["state"]["elapsed_regulation_minutes"] = 90
        self.assertEqual(evaluate(case)["status"], "HOLD")
        case = sample()
        case["final_score"] = [0, 2]
        self.assertEqual(evaluate(case)["status"], "HOLD")

    def test_cannot_inject_quote_or_verified_ev(self):
        for key, value in (("quote", {"away_handicap_win": 2.31}),
                           ("positive_ev_verified", True),
                           ("authenticated", True)):
            case = sample()
            case[key] = value
            self.assertEqual(evaluate(case)["status"], "HOLD")

    def test_project_rejects_invalid_numbers(self):
        for goals in (True, float('nan'), -1, 99):
            with self.assertRaises(ValueError):
                _project(0, 0, goals, 0, 1)
        with self.assertRaises(ValueError):
            _project(0, 0, 0.2, 0.3, 0.5)

    def test_sensitivity_three_scenarios_are_not_calibration(self):
        r = evaluate(sample())
        self.assertEqual([x["goal_rate_multiplier"] for x in r["scenarios"]], [.85, 1.0, 1.15])
        self.assertIs(r["probabilities_calibrated"], False)
        self.assertEqual(r["certified_forward_samples"], 0)


if __name__ == "__main__":
    unittest.main()
