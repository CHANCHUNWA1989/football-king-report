"""Pure synthetic tests; no external feeds, credentials, or certified forecasts."""
import copy
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_remaining_goal_baseline import evaluate, _scenario


def sample():
    return {"fixture": {"fixture_id": "event_123", "home_id": "river",
                        "away_id": "lanus", "kickoff_utc": "2026-11-23T00:00:00Z"},
            "prematch": {"home_goals_per_90": 1.5, "away_goals_per_90": 1.1,
                         "generated_utc": "2026-11-22T23:30:00Z",
                         "origin": "UNATTESTED_RESEARCH_ASSUMPTION"},
            "state": {"fixture_id": "event_123", "observed_utc": "2026-11-23T00:52:00Z",
                      "as_of_utc": "2026-11-23T00:52:10Z", "match_status": "HALF_TIME",
                      "elapsed_regulation_minutes": 45, "home_goals": 1, "away_goals": 1,
                      "home_red_cards": 0, "away_red_cards": 0}}


class InPlayRemainingBaselineTests(unittest.TestCase):
    def test_valid_half_time_math_is_research_only_not_betting(self):
        r = evaluate(sample())
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["model_scoring_eligible"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["event_source_authenticated"])
        self.assertFalse(r["probabilities_calibrated"])
        self.assertIsNone(r["recommendation"])
        mid = r["scenarios"][1]
        self.assertAlmostEqual(mid["assumed_remaining_home_goals"], .75)
        self.assertAlmostEqual(mid["assumed_remaining_away_goals"], .55)
        self.assertAlmostEqual(sum(mid[k] for k in ("home_win", "draw", "away_win")), 1, places=6)
        self.assertAlmostEqual(mid["at_least_one_more_goal"], 1-math.exp(-1.3), places=6)
        self.assertGreater(mid["over_2_5"], mid["over_3_5"])

    def test_intensity_sensitivity_is_monotone_for_more_goals(self):
        r = evaluate(sample())
        self.assertEqual([x["goal_rate_multiplier"] for x in r["scenarios"]], [.85, 1.0, 1.15])
        self.assertLess(r["scenarios"][0]["over_2_5"], r["scenarios"][2]["over_2_5"])

    def test_time_remaining_shrinks_hypothetical_rate(self):
        c = sample()
        half = evaluate(c)["scenarios"][1]
        c["state"].update({"match_status": "SECOND_HALF", "elapsed_regulation_minutes": 75,
                           "observed_utc": "2026-11-23T01:30:00Z",
                           "as_of_utc": "2026-11-23T01:30:10Z"})
        late = evaluate(c)["scenarios"][1]
        self.assertLess(late["assumed_remaining_home_goals"], half["assumed_remaining_home_goals"])

    def test_lead_is_shifted_by_existing_score(self):
        self.assertGreater(_scenario(2, 0, .3, .3)["home_win"], .9)
        self.assertLess(_scenario(0, 0, .3, .3)["home_win"], .5)

    def test_missing_cards_fail_closed_no_inferred_zero(self):
        c = sample()
        c["state"].pop("home_red_cards")
        self.assertEqual(evaluate(c)["status"], "HOLD")

    def test_any_red_card_holds_without_trained_effect(self):
        for field in ("home_red_cards", "away_red_cards"):
            c = sample()
            c["state"][field] = 1
            self.assertEqual(evaluate(c)["status"], "HOLD")
            self.assertEqual(evaluate(c)["scenarios"], [])

    def test_mismatched_match_identity(self):
        c = sample()
        c["state"]["fixture_id"] = "other"
        self.assertEqual(evaluate(c)["reason"], "FIXTURE_IDENTITY_CONFLICT")

    def test_no_lookahead_or_forged_prematch_time(self):
        for stamp in ("2026-11-23T00:05:00Z", "2026-11-22T23:58:00Z", "2026-11-22T23:30:00"):
            c = sample()
            c["prematch"]["generated_utc"] = stamp
            self.assertEqual(evaluate(c)["status"], "HOLD")

    def test_stale_and_future_snapshot(self):
        for stamp in ("2026-11-23T00:55:00Z", "2026-11-23T00:49:00Z"):
            c = sample()
            c["state"]["as_of_utc"] = stamp
            self.assertEqual(evaluate(c)["status"], "HOLD")

    def test_impossible_clock_and_completed_game(self):
        c = sample()
        c["state"]["elapsed_regulation_minutes"] = 85
        self.assertEqual(evaluate(c)["status"], "HOLD")
        c = sample()
        c["state"].update({"match_status": "FINISHED", "elapsed_regulation_minutes": 90})
        self.assertEqual(evaluate(c)["status"], "HOLD")

    def test_nan_bool_and_unsupported_extra_authenticity_flag(self):
        for fld, val in (("home_goals_per_90", float("nan")),
                         ("home_goals_per_90", True), ("away_goals_per_90", 10.0)):
            c = sample()
            c["prematch"][fld] = val
            self.assertEqual(evaluate(c)["status"], "HOLD")
        c = sample()
        c["officially_verified"] = True
        self.assertEqual(evaluate(c)["status"], "HOLD")

    def test_mutations_do_not_touch_original(self):
        c = sample()
        original = copy.deepcopy(c)
        evaluate(c)
        self.assertEqual(c, original)

    def test_0_0_second_half_probability_normalizes(self):
        c = sample()
        c["state"].update({"home_goals": 0, "away_goals": 0,
                           "match_status": "SECOND_HALF", "elapsed_regulation_minutes": 60,
                           "observed_utc": "2026-11-23T01:16:00Z",
                           "as_of_utc": "2026-11-23T01:16:02Z"})
        r = evaluate(c)
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(sum(r["scenarios"][1][k] for k in
                         ("home_win", "draw", "away_win")), 1, places=6)


if __name__ == "__main__":
    unittest.main()
