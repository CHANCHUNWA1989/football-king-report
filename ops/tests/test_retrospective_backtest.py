"""Retrospective date-cutoff replay must never masquerade as prospective picks."""
import copy
import hashlib
import json
import math
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_backtest import (
    build, parse_archive, replay, draw_adjust, frequency_baseline,
    evaluate_cohort, block_ci, MIN_HOLDOUT, choose_prior_blend, blend_with_prior,
)
import retrospective_backtest as replay_module


class RetrospectiveReplayTests(unittest.TestCase):
    def setUp(self):
        start = date(2025, 8, 1)
        clubs = ["A", "B", "C", "D", "E", "F"]
        self.fixture_rows = []
        # A deliberately synthetic, valid history used ONLY in unit tests.
        for i in range(120):
            self.fixture_rows.append({
                "date": (start + timedelta(days=i)).isoformat(),
                "team1": clubs[i % len(clubs)],
                "team2": clubs[(i + 1) % len(clubs)],
                "score": {"ft": [i % 4, (i + 1) % 3]},
            })

    def test_parse_accepts_finished_ft_and_rejects_future_without_guessing_time(self):
        doc = {"name": "Synthetic", "matches": copy.deepcopy(self.fixture_rows)}
        matches, missing = parse_archive(doc)
        self.assertEqual(len(matches), 120)
        self.assertEqual(missing, {})
        self.assertTrue(all("kickoff_utc" not in row for row in matches))

    def test_model_is_replayed_using_only_previous_calendar_day_results(self):
        matches, _ = parse_archive({"matches": self.fixture_rows})
        first, skipped = replay(matches, "epl", "2025-26")
        self.assertGreater(len(first), 50)
        self.assertGreaterEqual(skipped["initial_less_than_30_games"], 30)
        # Altering a future-day final score cannot change any probability
        # issued in the date-only retrospective at earlier calendar cutoffs.
        changed = copy.deepcopy(matches)
        changed[-1]["score_ft"] = [20, 0]
        second, _ = replay(changed, "epl", "2025-26")
        self.assertEqual([x["original"] for x in first],
                         [x["original"] for x in second])
        self.assertEqual(first[-1]["training_games"], 119)

    def test_earliest_team_seen_only_after_30_results_is_skipped(self):
        rows = copy.deepcopy(self.fixture_rows)
        rows[-1]["team1"] = "Unseen Club"
        matches, _ = parse_archive({"matches": rows})
        samples, excluded = replay(matches, "epl", "2025-26")
        self.assertEqual(excluded["not_predicted_with_prior_history"], 1)
        self.assertTrue(all(sum(row["original"]) > 0.999 for row in samples))

    def test_predeclared_draw_challenger_moves_exact_three_points(self):
        old = [0.6, 0.22, 0.18]
        new = draw_adjust(old)
        self.assertAlmostEqual(sum(new), 1.0)
        self.assertAlmostEqual(new[1], old[1] + 0.03)
        self.assertGreater(old[0], new[0])
        self.assertEqual(max(range(3), key=new.__getitem__), 0)

    def test_frequency_baseline_uses_only_past_scores(self):
        past = [{"score_ft": [1, 0]} for _ in range(4)]
        p = frequency_baseline(past)
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], 0.45)
        self.assertEqual(len(p), 3)

    def test_baseline_report_and_honest_uncertainty(self):
        matches, _ = parse_archive({"matches": self.fixture_rows})
        rows, _ = replay(matches, "epl", "2025-26")
        e = evaluate_cohort(rows)
        self.assertGreater(e["n"], 50)
        self.assertEqual(e["original"]["n"], len(rows))
        self.assertEqual(len(e["coverage_at_confidence_cutoffs"]), 4)
        self.assertTrue(math.isfinite(e["original"]["mean_log_loss"]))
        self.assertFalse(e["original"]["draw_calibration_gap"] is None)
        self.assertIsNotNone(block_ci(rows, "draw_adjust", repetitions=1000))

    def test_prior_shrink_weight_chosen_exclusively_from_development_data(self):
        rows = [
            {"original": [.6, .2, .2], "league_frequency": [.3, .4, .3],
             "y": i % 3} for i in range(70)
        ]
        fit = choose_prior_blend(rows)
        self.assertEqual(fit["basis"], "2024_25_DEVELOPMENT_LOG_LOSS_ONLY")
        self.assertIn(fit["weight"], (0.0, .1, .2, .3, .4))
        self.assertEqual(len(fit["scores"]), 5)
        original = fit.copy()
        extra_holdout_that_must_be_ignored = [
            {"original": [.1, .1, .8], "league_frequency": [.8, .1, .1],
             "y": 0} for _ in range(500)]
        self.assertEqual(choose_prior_blend(rows), original)
        # The alternative holdout records are deliberately never passed to fit.
        self.assertEqual(len(extra_holdout_that_must_be_ignored), 500)

    def test_prior_blend_never_invents_or_renormalizes_bad_probabilities(self):
        blended = blend_with_prior([.7, .2, .1], [.4, .3, .3], .2)
        self.assertAlmostEqual(sum(blended), 1.0)
        self.assertAlmostEqual(blended[0], .64)
        with self.assertRaises(ValueError):
            blend_with_prior([.7, .2, .9], [.4, .3, .3], .2)
        with self.assertRaises(ValueError):
            blend_with_prior([.7, .2, .1], [.4, .3, .3], .8)

    def test_archive_shortfall_stays_research_disabled(self):
        doc = {"matches": self.fixture_rows}
        result = build({("2025-26", "epl"): (doc, hashlib.sha256(
            json.dumps(doc).encode()).hexdigest())})
        self.assertEqual(result["holdout_season_samples"],
                         result["cohorts"]["2025-26"]["n"])
        self.assertLess(result["holdout_season_samples"], MIN_HOLDOUT)
        self.assertEqual(result["interpretation"],
                         "INSUFFICIENT_RETROSPECTIVE_HOLDOUT_COVERAGE")
        self.assertFalse(result["live_point_in_time_forecasts_verified"])
        self.assertFalse(result["betting_roi_estimable"])
        self.assertFalse(result["automatic_model_promotion"])
        self.assertFalse(result["prior_blend_automatic_promotion_permitted"])
        self.assertFalse(result["prior_blend_uses_holdout_labels_for_tuning"])
        self.assertTrue(result["holdout_has_already_been_inspected_previously"])
        self.assertIsNotNone(result["prior_blend_holdout"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertTrue(result["replay_adapter_time_is_not_a_real_kickoff"])


class ReplayErrorDiagnosticTests(unittest.TestCase):
    def row(self, n=0, *, original=None, baseline=None, y=1):
        return {"league":"epl", "season":"2025-26", "date":"2025-10-05",
                "replay_case_id":f"epl|2025-26|2025-10-05|{n}",
                "replay_case_id_kind":"DERIVED_LOCAL_REPLAY_NOT_PROVIDER_NATIVE",
                "home":"Home", "away":"Away", "training_games":100,
                "training_cutoff_local_day":"2025-10-04",
                "training_observations_sha256":"a"*64,
                "original":original or [.6,.2,.2],
                "league_frequency":baseline or [.4,.3,.3], "y":y,
                "score_ft":[1,1] if y==1 else [2,0] if y==0 else [0,2]}

    def diagnose(self, rows):
        return replay_module.error_diagnostics(rows)

    def test_confusion_orientation_class_bias_and_tie_policy(self):
        rows=[self.row(0,y=0),self.row(1,y=1),
              self.row(2,original=[.1,.3,.6],y=1),
              self.row(3,original=[.4,.4,.2],y=2)]
        result=self.diagnose(rows)
        self.assertEqual(result["outcome_order"],["home","draw","away"])
        model=result["models"]["original"]
        self.assertEqual(model["confusion_matrix_actual_rows_predicted_columns"],
                         [[1,0,0],[1,0,1],[1,0,0]])
        home,draw,away=model["per_outcome"]
        self.assertEqual((home["actual_count"],home["predicted_count"]),(1,3))
        self.assertEqual(home["precision"],round(1/3,6))
        self.assertEqual(home["recall"],1.0)
        self.assertIsNone(draw["precision"])
        self.assertEqual(draw["recall"],0.0)
        self.assertEqual(draw["mean_forecast_probability"],.275)
        self.assertEqual(draw["observed_fraction"],.5)
        self.assertEqual(draw["calibration_gap"],-.225)
        self.assertEqual(away["recall"],0.0)
        self.assertEqual(result["models"]["league_frequency"][
            "confusion_matrix_actual_rows_predicted_columns"],[[1,0,0],[2,0,0],[1,0,0]])

    def test_fixed_bins_reuse_outcome_calibration_and_compute_unrounded_ece(self):
        from research_center import calibration
        rows=[self.row(0,original=[.4,.35,.25],y=0),
              self.row(1,original=[.5999992,.2,.2000008],y=1),
              self.row(2,original=[.6,.2,.2],y=0),
              self.row(3,original=[.9000016,.05,.0499984],y=2)]
        model=self.diagnose(rows)["models"]["original"]
        bins=model["top_choice_confidence_bins"]
        self.assertEqual(len(bins),5)
        self.assertEqual([b["n"] for b in bins],[0,0,2,1,1])
        self.assertIsNone(bins[0]["mean_confidence"])
        self.assertEqual(bins[2]["observed_accuracy"],.5)
        expected=(abs(.4+.5999992-1)+abs(.6-1)+abs(.9000016-0))/4
        self.assertEqual(model["top_choice_expected_calibration_error"],round(expected,6))
        self.assertEqual(model["probability_calibration"],
                         calibration([{"p":r["original"],"y":r["y"]} for r in rows]))

    def test_worst_positive_excess_examples_are_traced_bounded_and_deterministic(self):
        rows=[self.row(n) for n in reversed(range(8))]
        rows.append(self.row(8,original=[.2,.6,.2]))  # Better than frequency.
        result=self.diagnose(rows)
        cases=result["worst_excess_log_loss_cases"]
        self.assertEqual(len(cases),5)
        self.assertEqual([x["replay_case_id"] for x in cases],
                         [self.row(n)["replay_case_id"] for n in range(5)])
        self.assertEqual(cases,self.diagnose(list(reversed(rows)))["worst_excess_log_loss_cases"])
        expected=-math.log(.2)+math.log(.3)
        self.assertEqual(cases[0]["excess_log_loss_original_minus_frequency"],round(expected,6))
        self.assertEqual(cases[0]["original"],[.6,.2,.2])
        self.assertEqual(cases[0]["league_frequency"],[.4,.3,.3])
        self.assertEqual(cases[0]["score_ft"],[1,1])
        self.assertEqual(cases[0]["training_cutoff_local_day"],"2025-10-04")
        self.assertEqual(cases[0]["training_observations_sha256"],"a"*64)
        self.assertFalse(cases[0]["authentic_prematch_prediction"])
        self.assertFalse(result["source_results_independently_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_missing_or_invalid_optional_trace_keeps_counts_without_inventing_examples(self):
        rows=[{"original":[.6,.2,.2],"league_frequency":[.4,.3,.3],"y":1},
              self.row(1)]
        rows[1]["training_cutoff_local_day"]="2025-10-05"  # Not earlier.
        result=self.diagnose(rows)
        self.assertEqual(result["n"],2)
        self.assertEqual(result["rows_without_case_trace"],2)
        self.assertEqual(result["worst_excess_log_loss_cases"],[])
        self.assertEqual(result["models"]["original"]["per_outcome"][1]["actual_count"],2)

    def test_malformed_probabilities_and_outcomes_fail_without_fake_counts(self):
        bad=[]
        for key,value in (("y",True),("y",-1),("y",3),("y",.0),
                          ("original",[True,.2,.2]),("original",[float("nan"),.2,.8]),
                          ("original",[float("inf"),.2,.8]),("original",[.5,.2]),
                          ("original",[.5,.2,.9]),("original",[10**1000,.2,.8]),
                          ("league_frequency",None),("league_frequency",[.4,.3,".3"])):
            row=self.row();row[key]=value;bad.append(row)
        for row in bad+[None,{},[]]:
            with self.subTest(row=repr(row)[:120]):
                with self.assertRaises(ValueError):self.diagnose([row])
        with self.assertRaises(ValueError):self.diagnose([self.row(),self.row()])

    def test_empty_diagnostics_are_stable_json_without_nan(self):
        result=self.diagnose([])
        self.assertEqual(result["n"],0)
        self.assertEqual(result["rows_without_case_trace"],0)
        self.assertEqual(result["worst_excess_log_loss_cases"],[])
        for model in result["models"].values():
            self.assertEqual(model["confusion_matrix_actual_rows_predicted_columns"],[[0]*3 for _ in range(3)])
            self.assertIsNone(model["top_choice_expected_calibration_error"])
            self.assertTrue(all(b["n"]==0 for b in model["top_choice_confidence_bins"]))
        json.dumps(result,allow_nan=False)

    def test_diagnostics_do_not_mutate_inputs_or_return_probability_aliases(self):
        rows=[self.row()];old=copy.deepcopy(rows)
        result=self.diagnose(rows)
        self.assertEqual(rows,old)
        result["worst_excess_log_loss_cases"][0]["original"][0]=.1
        result["worst_excess_log_loss_cases"][0]["score_ft"][0]=9
        self.assertEqual(rows,old)

    def test_existing_replay_supplies_trace_and_cohort_publishes_diagnostics(self):
        fixture=RetrospectiveReplayTests();fixture.setUp()
        matches,_=parse_archive({"matches":fixture.fixture_rows})
        rows,_=replay(matches,"epl","2025-26")
        for row in rows:
            self.assertTrue(row["replay_case_id"].startswith("epl|2025-26|"))
            self.assertEqual(row["replay_case_id_kind"],"DERIVED_LOCAL_REPLAY_NOT_PROVIDER_NATIVE")
            self.assertLess(row["training_cutoff_local_day"],row["date"])
            self.assertEqual(len(row["training_observations_sha256"]),64)
            self.assertNotEqual(row["home"],row["away"])
        result=evaluate_cohort(rows)
        self.assertEqual(result["error_diagnostics"],self.diagnose(rows))
        self.assertEqual(result["error_diagnostics"]["rows_without_case_trace"],0)


if __name__ == "__main__":
    unittest.main()
