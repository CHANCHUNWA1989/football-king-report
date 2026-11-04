"""Synthetic as-of dynamic comeback model tests, zero network."""
import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_state_challenger_vnext import audit_predict, predict, remaining_matrix

KO = "2026-11-03T20:00:00Z"


def sample(*, score=(0, 2), minute=45, decision="2026-11-03T20:49:00Z",
           reds=(0, 0), home_rate=1.65, away_rate=1.4):
    return {
        "fixture_id": "synthetic-ucl-001",
        "kickoff_utc": KO,
        "decision_utc": decision,
        "minute_elapsed": minute,
        "score_home": score[0], "score_away": score[1],
        "red_home": reds[0], "red_away": reds[1],
        "prematch": {
            "fixture_id": "synthetic-ucl-001",
            "model_id": "research-poisson-sealed-v0",
            "forecast_utc": "2026-11-03T19:45:00Z",
            "inputs_available_utc": "2026-11-03T19:40:00Z",
            "expected_home_goals": home_rate, "expected_away_goals": away_rate,
            "input_sha256": "a" * 64, "calibrated": False,
            "production_recommendations": "DISABLED",
        },
        "event_consensus": {
            "fixture_id": "synthetic-ucl-001",
            "decision_utc": decision, "status": "RESEARCH_ONLY",
            "score_home": score[0], "score_away": score[1],
            "active_red_cards": {"HOME": reds[0], "AWAY": reds[1]},
            "evidence_input_sha256": "b" * 64,
            "source_authenticated": False,
            "source_independence_verified": False,
            "model_scoring_eligible": False,
            "production_recommendations": "DISABLED",
        },
    }


class InplayChallengerTests(unittest.TestCase):
    def test_research_only_normalized_1x2_and_comeback(self):
        output = predict(sample())
        self.assertEqual(output["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(sum(output["fulltime_probabilities"].values()), 1.0, places=10)
        self.assertEqual(output["trailing_team"], "HOME")
        self.assertEqual(output["trailing_team_comeback_win_probability"],
                         output["fulltime_probabilities"]["HOME"])
        for key in ("model_calibrated", "model_scoring_eligible",
                    "source_authenticated", "positive_ev_verified",
                    "betting_recommendation_allowed"):
            self.assertFalse(output[key])
        self.assertEqual(output["production_recommendations"], "DISABLED")

    def test_two_goal_deficit_less_likely_to_reverse_near_end(self):
        first = predict(sample())
        late = predict(sample(minute=85, decision="2026-11-03T21:29:00Z"))
        self.assertGreater(first["trailing_team_comeback_win_probability"],
                           late["trailing_team_comeback_win_probability"])

    def test_no_deficit_returns_null_comeback(self):
        r = predict(sample(score=(1, 1)))
        self.assertIsNone(r["trailing_team"])
        self.assertIsNone(r["trailing_team_comeback_win_probability"])

    def test_away_trailing_uses_away_probability(self):
        r = predict(sample(score=(2, 0)))
        self.assertEqual(r["trailing_team"], "AWAY")
        self.assertEqual(r["trailing_team_comeback_win_probability"],
                         r["fulltime_probabilities"]["AWAY"])

    def test_confirmed_red_to_trailing_home_reduces_comeback_illustratively(self):
        baseline = predict(sample())
        disadvantage = predict(sample(reds=(1, 0)))
        self.assertLess(disadvantage["trailing_team_comeback_win_probability"],
                        baseline["trailing_team_comeback_win_probability"])

    def test_latest_inplay_red_mismatch_fails_closed(self):
        s = sample()
        s["red_home"] = 1
        self.assertEqual(audit_predict(s)["reason"], "CONFLICTING_OR_UNTRUSTED_CONSENSUS")

    def test_scoreboard_mismatch_fails_closed(self):
        s = sample()
        s["score_home"] = 3
        self.assertEqual(audit_predict(s)["status"], "HOLD")

    def test_forecast_after_prediction_or_kickoff_refused(self):
        for k, v in (("forecast_utc", "2026-11-03T19:59:00Z"),
                     ("inputs_available_utc", "2026-11-03T19:46:00Z")):
            with self.subTest(field=k):
                s = sample()
                s["prematch"][k] = v
                self.assertEqual(audit_predict(s)["reason"], "PREMATCH_LOOKAHEAD_OR_UNSEALED")

    def test_post_decision_feed_cannot_rewrite_past_predictions(self):
        s = sample()
        s["event_consensus"]["decision_utc"] = "2026-11-03T20:52:00Z"
        self.assertEqual(audit_predict(s)["status"], "HOLD")

    def test_missing_event_consensus_refuses(self):
        s = sample()
        s["event_consensus"] = {}
        self.assertEqual(audit_predict(s)["reason"], "MISSING_RESEARCH_EVENT_CONSENSUS")

    def test_partial_or_fake_source_certification_refused(self):
        s = sample()
        s["event_consensus"]["source_authenticated"] = True
        self.assertEqual(audit_predict(s)["status"], "HOLD")

    def test_calibrated_claim_cannot_be_smuggled(self):
        s = sample()
        s["prematch"]["calibrated"] = True
        self.assertEqual(audit_predict(s)["reason"], "INVALID_PREMATCH_ARCHIVE")

    def test_winning_label_or_bookmaker_quote_extra_fields_rejected(self):
        for name, value in (("final_result", "HOME"), ("odds", 2.1)):
            with self.subTest(name=name):
                s = sample()
                s[name] = value
                self.assertEqual(audit_predict(s)["reason"], "INVALID_INPLAY_SNAPSHOT_SCHEMA")

    def test_time_order_and_unsupported_stoppage_holds(self):
        s = sample(minute=90, decision="2026-11-03T21:35:00Z")
        self.assertEqual(audit_predict(s)["reason"], "UNSUPPORTED_INPLAY_MINUTE_OR_STOPPAGE")
        s = sample(minute=85, decision="2026-11-03T20:55:00Z")
        self.assertEqual(audit_predict(s)["reason"], "IMPOSSIBLE_OR_STALE_MATCH_CLOCK")

    def test_boolean_nan_and_negative_scores_rejected(self):
        for value in (True, -1, 11, 1.5):
            with self.subTest(value=value):
                s = sample()
                s["score_home"] = value
                s["event_consensus"]["score_home"] = value
                self.assertEqual(audit_predict(s)["status"], "HOLD")
        self.assertEqual(audit_predict(sample(home_rate=float("nan")))["status"], "HOLD")

    def test_remaining_matrix_shifts_onto_current_score(self):
        m = remaining_matrix(1.2, 0.8, 2, 1)
        self.assertAlmostEqual(sum(map(sum, m)), 1, places=10)
        self.assertEqual(sum(m[0]), 0)
        self.assertEqual(sum(m[1]), 0)
        self.assertEqual(m[2][0], 0)
        self.assertGreater(m[2][1], 0)

    def test_poisson_zero_remaining_means_deterministic_current_result(self):
        m = remaining_matrix(0, 0, 0, 2)
        self.assertEqual(m[0][2], 1.0)
        self.assertEqual(len(m), 1)
        self.assertEqual(len(m[0]), 3)

    def test_returned_probs_repeat_without_external_changes(self):
        s = sample()
        self.assertEqual(predict(s), predict(copy.deepcopy(s)))

    def test_stale_match_clock_refused(self):
        s = sample(minute=45, decision="2026-11-03T21:15:00Z")
        self.assertEqual(audit_predict(s)["reason"], "IMPOSSIBLE_OR_STALE_MATCH_CLOCK")

    def test_all_failures_keep_betting_disabled(self):
        r = audit_predict({})
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertFalse(r["positive_ev_verified"])


if __name__ == "__main__":
    unittest.main()
