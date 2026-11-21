"""Repeatable offline historical research replay and adversarial regressions."""
import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from ops.calibration_evidence_readiness import read_archive
from ops.historical_research_stress import stress, _score

UTC = timezone.utc
KICK = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


def case(index, result=1):
    return {
        "key": "synthetic:fixture:" + str(index),
        "league": "bundesliga",
        "kickoff_utc": KICK.isoformat(),
        "forecast_utc": (KICK-timedelta(hours=6)).isoformat(),
        "market_utc": (KICK-timedelta(hours=7)).isoformat(),
        "y": result,
        "p": [0.6, 0.3, 0.1],
        "m": [0.5, 0.3, 0.2],
        "production_recommendations": "DISABLED",
        "fixture_result_source_independently_verified": False,
    }


class HistoricalResearchStressTests(unittest.TestCase):
    def test_actual_archive_replays_deterministically_without_promotion(self):
        data = read_archive(REPO / "evidence" / "settled.json")
        result = stress(data)
        self.assertEqual(result["archive_rows"], len(data["samples"]))
        self.assertEqual(result["unique_scored_research_rows"], len(data["samples"]))
        self.assertEqual(result["calibration_gate"]["certified_rows"], 0)
        self.assertEqual(result["paired"]["A_vs_market"]["n"],
                         len(data["samples"]))
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["verified_oos_improvement"])
        self.assertFalse(result["actual_real_odd_quotes_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_research_score_recomputed_from_multiclass_outcome(self):
        result = stress({"samples": [case(1, 1)]})
        self.assertAlmostEqual(result["scores"]["A"]["brier"], .86)
        self.assertAlmostEqual(result["scores"]["A"]["log_loss"],
                               1.2039728)
        self.assertEqual(result["scores"]["A"]["argmax_correct"], 0)
        self.assertEqual(result["market_snapshot_older_than_4h_before_kickoff"], 1)
        self.assertEqual(result["market_age_hours_median"], 7.0)
        self.assertEqual(result["forecast_to_market_gap_hours_median"], 1.0)
        self.assertEqual(result["paired"]["A_vs_market"]["n"], 1)

    def test_old_model_ab_market_scores_use_identical_matched_fixture(self):
        base, extension = case(1), case(2)
        extension["ab"] = [0.5, 0.3, 0.2]
        extension["c"] = [0.5, 0.25, 0.25]
        report = stress({"samples": [base, extension]})
        self.assertEqual(report["scores"]["A"]["n"], 2)
        self.assertEqual(report["paired"]["B_vs_A"]["n"], 1)
        self.assertEqual(report["paired"]["C_vs_A"]["n"], 1)
        self.assertEqual(report["paired"]["B_vs_market"]["n"], 1)
        self.assertEqual(report["paired"]["C_vs_market"]["n"], 1)

    def test_same_rows_any_input_order_same_aggregate(self):
        rows = [case(i, i % 3) for i in range(1, 9)]
        first = stress({"samples": rows})
        last = stress({"samples": list(reversed(rows))})
        self.assertEqual(first["scores"], last["scores"])
        self.assertEqual(first["paired"], last["paired"])

    def test_duplicate_fixture_not_counted_twice(self):
        rows = [case(1), copy.deepcopy(case(1))]
        result = stress({"samples": rows})
        self.assertEqual(result["archive_rows"], 2)
        self.assertEqual(result["duplicate_case_keys"], 1)
        self.assertEqual(result["unique_scored_research_rows"], 1)

    def test_postkickoff_market_rejected(self):
        item = case(1)
        item["market_utc"] = (KICK+timedelta(seconds=1)).isoformat()
        report = stress({"samples": [item]})
        self.assertEqual(report["time_invalid_rows"], 1)
        self.assertEqual(report["unique_scored_research_rows"], 0)

    def test_postkickoff_forecast_rejected(self):
        item = case(1)
        item["forecast_utc"] = KICK.isoformat()
        self.assertEqual(stress({"samples": [item]})["time_invalid_rows"], 1)

    def test_false_certification_flags_still_do_not_verify_results(self):
        row = case(1)
        row.update({
            "fixture_result_source_independently_verified": True,
            "fixture_identity_independently_verified": True,
            "forecast_provenance_independently_attested": True,
        })
        report = stress({"samples": [row]})
        self.assertEqual(report["calibration_gate"]["certified_rows"], 0)
        self.assertFalse(report["external_provenance_verified"])
        self.assertFalse(report["calibration_gate"]["calibration_candidate_generated"])

    def test_boolean_result_rejected(self):
        item = case(1)
        item["y"] = True
        r = stress({"samples": [item]})
        self.assertEqual(r["skipped_rows"], 1)
        self.assertEqual(r["unique_scored_research_rows"], 0)

    def test_malformed_optional_c_challenger_fails_close(self):
        item = case(1)
        item["c"] = [0.9, 0.1, 0.1]
        r = stress({"samples": [item]})
        self.assertEqual(r["skipped_rows"], 1)
        self.assertEqual(r["unique_scored_research_rows"], 0)

    def test_ineligible_production_enabled_event_skipped(self):
        item = case(1)
        item["production_recommendations"] = "ENABLED"
        report = stress({"samples": [item]})
        self.assertEqual(report["unique_scored_research_rows"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_fixed_temperature_grid_is_not_trained_or_promoted(self):
        rows = [case(1, 1), case(2, 2)]
        report = stress({"samples": rows})
        fixed = report["fixed_temperature_sensitivity"]
        self.assertTrue(fixed["fixed_grid_only_not_training_or_forecast"])
        self.assertIsNone(fixed["selected_or_promoted_temperature"])
        self.assertEqual(set(fixed["all_archive_research"]),
                         {"1.0", "1.2", "1.5", "2.0"})
        self.assertEqual(fixed["all_archive_research"]["1.0"]["n"], 2)
        self.assertAlmostEqual(fixed["all_archive_research"]["1.0"]["brier"],
                               report["scores"]["A"]["brier"], places=6)
        for scores in fixed["all_archive_research"].values():
            self.assertGreaterEqual(scores["brier"], 0)
            self.assertEqual(scores["n"], 2)
        self.assertEqual(report["status"], "HOLD")

    def test_fixed_temperature_months_each_use_only_own_fixtures(self):
        first = case(1)
        second = case(2)
        second["kickoff_utc"] = (KICK + timedelta(days=30)).isoformat()
        second["forecast_utc"] = (KICK + timedelta(days=30, hours=-6)).isoformat()
        second["market_utc"] = (KICK + timedelta(days=30, hours=-7)).isoformat()
        fixed = stress({"samples": [first, second]})["fixed_temperature_sensitivity"]
        self.assertEqual(fixed["by_month_research"]["2026-10"]["1.5"]["n"], 1)
        self.assertEqual(fixed["by_month_research"]["2026-11"]["1.5"]["n"], 1)
        self.assertIsNone(fixed["selected_or_promoted_temperature"])

    def test_bad_archive_fails_closed(self):
        for payload in (None, {}, [], {"samples": None}, {"samples": 1}):
            with self.subTest(payload=payload):
                report = stress(payload)
                self.assertEqual(report["status"], "HOLD")
                self.assertEqual(report["reason"], "INVALID_ARCHIVE_FORMAT")

    def test_input_archive_never_mutated(self):
        payload = {"samples": [case(1)]}
        before = copy.deepcopy(payload)
        stress(payload)
        self.assertEqual(payload, before)

    def test_by_league_and_month_cannot_inflate_counts(self):
        one = case(1)
        two = case(2)
        two["league"] = "epl"
        two["kickoff_utc"] = (KICK+timedelta(days=30)).isoformat()
        two["forecast_utc"] = (KICK+timedelta(days=30)-timedelta(hours=8)).isoformat()
        two["market_utc"] = (KICK+timedelta(days=30)-timedelta(hours=9)).isoformat()
        out = stress({"samples": [one, two]})
        self.assertEqual(out["by_league"]["bundesliga"]["n"], 1)
        self.assertEqual(out["by_league"]["epl"]["n"], 1)
        self.assertEqual(out["by_month"]["2026-10"]["n"], 1)
        self.assertEqual(out["by_month"]["2026-11"]["n"], 1)


if __name__ == "__main__":
    unittest.main()
