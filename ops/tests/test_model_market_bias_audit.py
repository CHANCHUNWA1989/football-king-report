"""Archived model-market comparisons must be paired, time-valid and never a bet."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_market_bias_audit import audit
from research_center import build


def sample(i=0, league="epl", days=0):
    kickoff = datetime(2026, 10, 12, tzinfo=timezone.utc) + timedelta(days=days)
    return {
        "key": f"fixture-{i}", "league": league,
        "market_utc": (kickoff - timedelta(hours=5)).isoformat(),
        "forecast_utc": (kickoff - timedelta(hours=4)).isoformat(),
        "kickoff_utc": kickoff.isoformat(),
        "y": 0, "p": [.70, .20, .10], "m": [.45, .30, .25],
        "fixture_result_source_independently_verified": False,
        "production_recommendations": "DISABLED",
    }


NOW = "2027-02-01T00:00:00Z"


class MarketBiasAuditTests(unittest.TestCase):
    def test_empty_archive_never_fakes_metrics(self):
        a = audit([], archived_at_utc=NOW)
        self.assertEqual(a["status"], "HOLD")
        self.assertIsNone(a["diagnostics"])

    def test_paired_realistic_small_sample_detects_home_concentration(self):
        cases = [sample(i, days=i) for i in range(4)]
        cases[0]["y"] = 2
        r = audit(cases, archived_at_utc=NOW)
        d = r["diagnostics"]
        self.assertEqual(d["model_home_top_count"], 4)
        self.assertEqual(d["market_home_top_count"], 4)
        self.assertEqual(d["actual_home_wins_count"], 3)
        self.assertEqual(d["remaining_to_300"], 296)
        self.assertIsNone(d["paired_week_block_bootstrap_95pct_ci"])
        self.assertEqual(d["model_top_choice_correct"], 3)
        self.assertFalse(r["model_market_advantage_proven"])
        self.assertFalse(r["betting_ev_verified"])
        self.assertEqual(r["recommended_bets"], [])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_different_market_baseline_is_not_merged(self):
        row = sample()
        row["m"] = [.20, .30, .50]
        report = audit([row], archived_at_utc=NOW)["diagnostics"]
        self.assertEqual(report["model_home_top_count"], 1)
        self.assertEqual(report["market_home_top_count"], 0)
        self.assertGreater(report["market_minus_model_log_loss"], 0)

    def test_duplicate_and_time_leakage_are_hard_failure(self):
        a = sample()
        for cases in ([a, copy.deepcopy(a)],):
            with self.assertRaisesRegex(ValueError, "DUPLICATE"):
                audit(cases, archived_at_utc=NOW)
        a["market_utc"] = a["kickoff_utc"]
        with self.assertRaisesRegex(ValueError, "UNSAFE_ARCHIVED_TIME_ORDER"):
            audit([a], archived_at_utc=NOW)
        b = sample()
        with self.assertRaisesRegex(ValueError, "UNSAFE_ARCHIVED_TIME_ORDER"):
            audit([b], archived_at_utc="2026-10-11T00:00:00Z")

    def test_false_result_and_fake_boolean_probabilities_are_rejected(self):
        a = sample()
        for y in (False, True, 3, "0"):
            a["y"] = y
            with self.assertRaises(ValueError):
                audit([a], archived_at_utc=NOW)
        a["y"] = 0
        a["p"] = [True, .0, 0]
        with self.assertRaises(ValueError):
            audit([a], archived_at_utc=NOW)
        a["p"] = [.7, .2, .1]
        a["production_recommendations"] = "ENABLED"
        with self.assertRaises(ValueError):
            audit([a], archived_at_utc=NOW)

    def test_descriptive_week_bootstrap_still_never_promotes(self):
        leagues = ("epl", "bundesliga", "laliga", "seriea")
        rows = [sample(i, league=leagues[i % 4], days=(i % 84))
                for i in range(300)]
        one = audit(rows, archived_at_utc=NOW)
        other = audit(rows, archived_at_utc=NOW)
        d = one["diagnostics"]
        self.assertTrue(d["descriptive_coverage_thresholds_met"])
        self.assertEqual(d["independent_week_blocks"], 12)
        self.assertEqual(d["paired_week_block_bootstrap_95pct_ci"],
                         other["diagnostics"]["paired_week_block_bootstrap_95pct_ci"])
        self.assertIsNotNone(d["paired_week_block_bootstrap_95pct_ci"])
        self.assertFalse(one["model_market_advantage_proven"])
        self.assertEqual(one["production_recommendations"], "DISABLED")


    def test_research_center_includes_audit_without_model_promotion(self):
        fixture = sample()
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            docs = {
                "status.json": {"status": "RESEARCH_ONLY",
                                "production_recommendations": "DISABLED",
                                "checked_utc": NOW},
                "market_status.json": {"source_state": "RESEARCH_ONLY",
                                       "matched_count": 0,
                                       "production_recommendations": "DISABLED"},
                "validation.json": {"status": "HOLD"},
                "crosscheck.json": {},
                "league_coverage.json": {"production_recommendations": "DISABLED",
                                         "league_coverage": []},
                "ab_status.json": {"promotion_allowed": False},
                "shadow.json": {"predictions": [], "sources": [],
                                "predictions_count": 0},
                "market_comparison.json": {"comparisons": []},
            }
            for filename, data in docs.items():
                (folder / filename).write_text(json.dumps(data), encoding="utf-8")
            summary = build(folder, {
                "n": 1, "samples": [fixture], "checked_utc": NOW,
                "production_recommendations": "DISABLED"})
            report = summary["paired_model_market_bias_audit"]
            self.assertEqual(report["sample_count"], 1)
            self.assertEqual(report["diagnostics"]["model_home_top_count"], 1)
            self.assertEqual(summary["production_recommendations"], "DISABLED")
            self.assertFalse(report["model_market_advantage_proven"])


if __name__ == "__main__":
    unittest.main()
