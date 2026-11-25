"""Synthetic-only opponent-strength Poisson research tests; no real accuracy claims."""
import copy
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_forecast import predict_league
from opponent_adjusted_goals_challenger import (
    compare_shadow, _fit_goal_roles, MODEL, MIN_GAMES, RIDGE_EXPOSURE,
)

HK = ZoneInfo("Asia/Hong_Kong")
NOW = datetime(2026, 11, 21, 9, tzinfo=timezone.utc)
TEAMS = ("A", "B", "C", "D", "E", "F")
HOME_ATTACK = (2.1, 1.55, 1.1, .9, .65, .6)
AWAY_DEFENSE = (.75, .9, 1.0, 1.1, 1.35, 1.7)
AWAY_ATTACK = (1.5, 1.3, 1.0, 1.0, .85, .65)
HOME_DEFENSE = (.75, .85, 1.0, 1.05, 1.3, 1.5)


def history(rounds=12):
    rows = []
    for week in range(rounds):
        for j, home in enumerate(TEAMS):
            away_index = (j + 1 + week % 5) % len(TEAMS)
            away = TEAMS[away_index]
            i = week * len(TEAMS) + j
            day = (NOW - timedelta(days=i + 1)).astimezone(HK).date().isoformat()
            gh = round(1.4 * HOME_ATTACK[j] * AWAY_DEFENSE[away_index])
            ga = round(1.05 * AWAY_ATTACK[away_index] * HOME_DEFENSE[j])
            rows.append({
                "date": day, "home": home, "away": away,
                "event_id": f"synthetic:history:{i}",
                "status": "FINISHED", "score_ft": [gh, ga],
                "kickoff_utc": None,
            })
    return rows


def scheduled(*, home="A", away="F", event="synthetic:future:1"):
    kickoff = NOW + timedelta(days=2)
    return {
        "date": kickoff.astimezone(HK).date().isoformat(),
        "home": home, "away": away, "event_id": event,
        "kickoff_utc": kickoff.isoformat(),
        "status": "SCHEDULED", "score_ft": None,
    }


def run(past=None, future=None):
    return compare_shadow(
        (history() if past is None else past)
        + ([scheduled()] if future is None else future),
        league="epl", now=NOW,
    )


class OpponentAdjustedGoalsTests(unittest.TestCase):
    def test_original_forecast_untouched_and_candidate_research_only(self):
        rows = history() + [scheduled()]
        old = predict_league(rows, "epl", NOW)[0]
        report = compare_shadow(rows, league="epl", now=NOW)
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["model"], MODEL)
        self.assertGreaterEqual(report["training_distinct_games"], MIN_GAMES)
        self.assertEqual(report["ridge_pseudo_exposure"], RIDGE_EXPOSURE)
        pair = report["comparisons"][0]
        self.assertEqual(
            pair["original_shadow"]["p_home"],
            old["p_home"],
        )
        self.assertEqual(
            pair["original_shadow"]["p_draw"],
            old["p_draw"],
        )
        self.assertEqual(
            pair["original_shadow"]["p_away"],
            old["p_away"],
        )
        self.assertEqual(pair["original_shadow"]["training_observations_sha256"],
                         old["training_observations_sha256"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        for flag in (
            "actual_score_sources_independently_verified",
            "fixture_identity_authenticated",
            "source_capture_attested",
            "real_odds_available",
            "official_xg_used",
            "probabilities_calibrated",
            "verified_oos_improvement",
            "positive_ev_verified",
            "eligible_for_formal_forward_scoring",
            "model_promoted",
        ):
            self.assertFalse(report[flag], flag)

    def test_opponent_roles_make_goal_rate_depend_on_defensive_strength(self):
        records = history()
        games = [
            (r["home"], r["away"], r["score_ft"][0], r["score_ft"][1])
            for r in records
        ]
        fit = _fit_goal_roles(games)
        self.assertGreater(fit["home_attack"]["A"], fit["home_attack"]["E"])
        self.assertGreater(fit["away_concede"]["F"],
                           fit["away_concede"]["A"])
        self.assertGreater(fit["home_attack"]["A"] *
                           fit["away_concede"]["F"],
                           fit["home_attack"]["E"] *
                           fit["away_concede"]["A"])

    def test_positive_probability_mass_and_finite_goal_rates(self):
        pair = run()["comparisons"][0]["candidate"]
        probs = [pair[k] for k in ("p_home", "p_draw", "p_away")]
        self.assertAlmostEqual(sum(probs), 1.0, places=6)
        self.assertTrue(all(0 < p < 1 for p in probs))
        self.assertTrue(all(math.isfinite(pair[k]) and .1 <= pair[k] <= 5.5
                            for k in ("expected_home_goals",
                                      "expected_away_goals")))
        self.assertGreater(pair["expected_home_goals"], .1)

    def test_deterministic_if_history_order_reversed(self):
        original = history()
        self.assertEqual(run(original), run(list(reversed(original))))

    def test_exact_duplicate_history_cannot_inflate_training(self):
        old = history()
        self.assertEqual(run(old), run(old + copy.deepcopy(old)))

    def test_conflicting_same_fixture_result_fails_closed(self):
        cases = history()
        bad = {**cases[0], "score_ft": [19, 0]}
        report = run(cases + [bad])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["reason"], "CONFLICTING_HISTORICAL_RESULT")

    def test_same_day_result_cannot_leak_into_training(self):
        cases = history()
        current = {**cases[0], "date": NOW.astimezone(HK).date().isoformat(),
                   "event_id": "synthetic:current", "score_ft": [20, 0]}
        self.assertEqual(run(cases), run(cases + [current]))

    def test_future_finished_result_cannot_leak_into_training(self):
        cases = history()
        future = {**cases[0],
                  "date": (NOW + timedelta(days=1)).astimezone(HK).date().isoformat(),
                  "event_id": "synthetic:tomorrow", "score_ft": [20, 0]}
        self.assertEqual(run(cases), run(cases + [future]))

    def test_conflicting_native_event_history_id_fails_closed(self):
        cases = history()
        bad = {**cases[1], "event_id": cases[0]["event_id"]}
        report = run(cases + [bad])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "CONFLICTING_HISTORY_SOURCE_EVENT_ID")

    def test_duplicate_future_event_id_with_conflicting_teams_fails_closed(self):
        cases = history() + [scheduled(), scheduled(away="C")]
        report = compare_shadow(cases, league="epl", now=NOW)
        self.assertEqual(report["status"], "HOLD")

    def test_missing_explicit_source_id_fails_closed(self):
        game = scheduled()
        del game["event_id"]
        self.assertEqual(run(future=[game])["status"], "HOLD")

    def test_future_with_filled_result_cannot_get_prediction(self):
        game = scheduled()
        game["score_ft"] = [2, 0]
        self.assertEqual(run(future=[game])["candidate_count"], 0)

    def test_small_history_not_enough_data(self):
        report = run(history(rounds=4))
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "INSUFFICIENT_OPPONENT_TRAINING_GAMES")

    def test_insufficient_team_venue_games_fails_closed(self):
        report = run(future=[scheduled(home="A", away="Z")])
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["candidate_count"], 0)

    def test_forged_past_date_with_future_kickoff_is_rejected(self):
        cases = history()
        forged = {**cases[0],
                  "date": (NOW - timedelta(days=80)).astimezone(HK).date().isoformat(),
                  "kickoff_utc": (NOW + timedelta(hours=5)).isoformat(),
                  "event_id": "synthetic:forged-finished-time",
                  "score_ft": [20, 0]}
        result = run(cases + [forged])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "HISTORICAL_KICKOFF_TIME_CONFLICT")
        self.assertEqual(result["candidate_count"], 0)

    def test_naive_past_result_kickoff_is_rejected(self):
        cases = history()
        forged = {**cases[0], "event_id": "synthetic:naive-time",
                  "date": (NOW - timedelta(days=80)).astimezone(HK).date().isoformat(),
                  "kickoff_utc": "2026-10-12T13:30:00"}
        result = run(cases + [forged])
        self.assertEqual(result["reason"], "HISTORICAL_KICKOFF_TIME_CONFLICT")

    def test_invalid_naive_model_clock_rejected(self):
        with self.assertRaises(ValueError):
            compare_shadow(history()+[scheduled()], league="epl",
                           now=datetime(2026, 11, 21))

    def test_invalid_league_never_promotes(self):
        report = compare_shadow(history()+[scheduled()],
                                league="aleague", now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_missing_data_and_oversized_input_fail_closed(self):
        self.assertEqual(compare_shadow(None, league="epl", now=NOW)["status"],
                         "HOLD")
        report = compare_shadow([{}] * 6001, league="epl", now=NOW)
        self.assertEqual(report["reason"], "INVALID_OR_OVERSIZED_INPUT")

    def test_no_market_or_result_or_xg_can_be_manufactured(self):
        result = run()
        self.assertFalse(result["real_odds_available"])
        self.assertFalse(result["source_capture_attested"])
        self.assertFalse(result["official_xg_used"])
        self.assertFalse(result["eligible_for_formal_forward_scoring"])
        self.assertEqual(result["comparisons"][0]["candidate"]["betting_eligible"],
                         False)

    def test_iteration_budget_exhausted_fails_closed(self):
        from unittest.mock import patch
        with patch("opponent_adjusted_goals_challenger.MAX_ITERATIONS", 1):
            result = run()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "OPPONENT_STRENGTH_FIT_NOT_CONVERGED")
        self.assertEqual(result["comparisons"], [])
        self.assertFalse(result["eligible_for_formal_forward_scoring"])

    def test_normal_fit_reports_convergence(self):
        result = run()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertIs(result["strength_fit_converged"], True)
        self.assertLess(result["strength_fit_last_change"], 1e-9)

    def test_zero_iteration_budget_does_not_pass_as_convergence(self):
        from unittest.mock import patch
        with patch("opponent_adjusted_goals_challenger.MAX_ITERATIONS", 0):
            result = run()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "OPPONENT_STRENGTH_FIT_NOT_CONVERGED")

    def test_extreme_outlier_scores_do_not_explode(self):
        cases = history()
        for case in cases:
            case["score_ft"] = [20, 0]
        result = run(cases)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        pair = result["comparisons"][0]["candidate"]
        self.assertGreaterEqual(pair["expected_home_goals"], .1)
        self.assertLessEqual(pair["expected_home_goals"], 5.5)
        self.assertAlmostEqual(sum(pair[k] for k in
                                   ("p_home", "p_draw", "p_away")), 1, places=5)


if __name__ == "__main__":
    unittest.main()
