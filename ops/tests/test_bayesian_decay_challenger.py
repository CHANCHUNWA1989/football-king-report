"""Synthetic only; never evidence of improved real-life predictions."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, date, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shadow_forecast import predict_league
from bayesian_decay_challenger import compare_shadow, MODEL, HALF_LIFE_DAYS, PRIOR_EXPOSURE

HK = ZoneInfo("Asia/Hong_Kong")
NOW = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)
TEAMS = ("A", "B", "C", "D", "E", "F")


def history(n=72):
    rows = []
    for i in range(n):
        day = (NOW - timedelta(days=i+1)).astimezone(HK).date().isoformat()
        rows.append({
            "date": day, "home": TEAMS[i%6], "away": TEAMS[(i+1)%6],
            "status": "FINISHED", "score_ft": [1+(i%3==0), int(i%4==0)],
            "kickoff_utc": None
        })
    return rows


def scheduled():
    ko = NOW + timedelta(days=2)
    return {
        "date": ko.astimezone(HK).date().isoformat(),
        "home": "A", "away": "B", "event_id": "synthetic:fixture:1",
        "kickoff_utc": ko.isoformat(), "status": "SCHEDULED",
        "score_ft": None
    }


def run(rows=None):
    return compare_shadow((history() if rows is None else rows) + [scheduled()],
                          league="epl", now=NOW)


class BayesianDecayCandidateTests(unittest.TestCase):
    def test_model_and_controls_never_certify_picks(self):
        r = run()
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertEqual(r["model"], MODEL)
        self.assertEqual(r["candidate_count"], 1)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertEqual(r["half_life_days"], HALF_LIFE_DAYS)
        self.assertEqual(r["prior_exposure_matches"], PRIOR_EXPOSURE)
        for key in ("forecast_capture_attested", "source_fixtures_authenticated",
                    "actual_score_sources_independently_verified",
                    "probabilities_calibrated", "positive_ev_verified",
                    "eligible_for_formal_forward_scoring"):
            self.assertFalse(r[key])

    def test_original_baseline_is_exactly_preserved(self):
        data = history() + [scheduled()]
        base = predict_league(data, "epl", NOW)[0]
        r = compare_shadow(data, league="epl", now=NOW)["comparisons"][0]
        self.assertEqual(
            [r["original_shadow"][key] for key in ("p_home", "p_draw", "p_away")],
            [base[key] for key in ("p_home", "p_draw", "p_away")]
        )
        self.assertEqual(r["original_shadow"]["model"], base["model"])

    def test_candidate_probabilities_normalize(self):
        r = run()["comparisons"][0]
        p = r["candidate"]
        self.assertAlmostEqual(p["p_home"]+p["p_draw"]+p["p_away"], 1, places=6)
        for key in ("p_home", "p_draw", "p_away"):
            self.assertGreater(p[key], 0)
            self.assertLess(p[key], 1)

    def test_recent_score_reversal_affects_candidate_but_not_old_model(self):
        rows = history()
        recent_high = copy.deepcopy(rows)
        old_high = copy.deepcopy(rows)
        for i, row in enumerate(rows):
            if row["home"] == "A":
                recent_high[i]["score_ft"][0] = 4 if i < 36 else 0
                old_high[i]["score_ft"][0] = 0 if i < 36 else 4
        first = run(recent_high)["comparisons"][0]
        second = run(old_high)["comparisons"][0]
        self.assertEqual(first["original_shadow"], second["original_shadow"])
        self.assertGreater(first["candidate"]["expected_home_goals"],
                           second["candidate"]["expected_home_goals"])

    def test_permutation_does_not_change_output(self):
        src = history()
        self.assertEqual(run(src), run(list(reversed(src))))

    def test_identical_history_duplicate_cannot_inflate_training(self):
        src = history()
        self.assertEqual(run(src), run(src + copy.deepcopy(src)))

    def test_same_day_result_leakage_excluded(self):
        src = history()
        forged = {**src[0], "date": NOW.astimezone(HK).date().isoformat(),
                  "score_ft": [20, 0]}
        self.assertEqual(run(src), run(src + [forged]))

    def test_future_result_leakage_excluded(self):
        src = history()
        forged = {**src[0], "date": (NOW+timedelta(days=2)).astimezone(
            HK).date().isoformat(), "score_ft": [20, 0]}
        self.assertEqual(run(src), run(src + [forged]))

    def test_conflicting_same_fixture_scores_poison_cohort(self):
        src = history()
        conflict = {**src[0], "score_ft": [19, 3]}
        r = run(src + [conflict])
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["candidate_count"], 0)

    def test_conflicting_fixture_schedule_rejected_by_original_base(self):
        rows = history() + [scheduled(), {**scheduled(), "away": "C"}]
        r = compare_shadow(rows, league="epl", now=NOW)
        self.assertEqual(r["status"], "HOLD")

    def test_scheduled_fixture_missing_explicit_source_id_rejected(self):
        fixture = scheduled()
        del fixture["event_id"]
        r = compare_shadow(history() + [fixture], league="epl", now=NOW)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["candidate_count"], 0)

    def test_filled_future_result_cannot_get_challenger_prediction(self):
        fixture = {**scheduled(), "score_ft": [1, 0]}
        r = compare_shadow(history() + [fixture], league="epl", now=NOW)
        self.assertEqual(r["candidate_count"], 0)

    def test_old_data_below_recency_weight_threshold_is_hold(self):
        src = history()
        for i, row in enumerate(src):
            row["date"] = (date(2024, 1, 1) + timedelta(days=i)).isoformat()
        r = run(src)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "INSUFFICIENT_RECENCY_WEIGHTED_HISTORY")

    def test_too_few_finished_matches_is_hold(self):
        self.assertEqual(run(history(8))["status"], "HOLD")

    def test_unrecognized_league_rejected(self):
        r = compare_shadow(history() + [scheduled()], league="aleague", now=NOW)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "LEAGUE_NOT_IN_ORIGINAL_SHADOW")

    def test_naive_analysis_time_rejected(self):
        with self.assertRaises(ValueError):
            compare_shadow(history() + [scheduled()], league="epl",
                           now=datetime(2026, 11, 21))

    def test_missing_and_non_list_input_cannot_score(self):
        for value in (None, {}, "abc", []):
            r = compare_shadow(value, league="epl", now=NOW)
            self.assertEqual(r["status"], "HOLD")
            self.assertEqual(r["candidate_count"], 0)

    def test_prospective_original_screenshot_is_not_fabricated(self):
        r = run()
        self.assertTrue(r["analysis_clock_is_supplied_not_attested"])
        self.assertFalse(r["eligible_for_formal_forward_scoring"])
        self.assertFalse(r["official_xg_available"])
        self.assertFalse(r["real_bookmaker_quotes_verified"])
        self.assertFalse(r["published_recommendations_enabled"])


if __name__ == "__main__":
    unittest.main()
