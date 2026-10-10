"""Japan 2025 archive is NOT real 2026/27 point-in-time proof."""
import copy
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jleague_research_audit import evaluate


class JapanJ1AuditTests(unittest.TestCase):
    def setUp(self):
        clubs = [
            "Cerezo Osaka", "Gamba Osaka", "Yokohama F. Marinos",
            "Urawa Reds", "Kawasaki Frontale", "Kyoto Sanga",
        ]
        start = date(2025, 2, 14)
        self.matches = [
            {"date": (start + timedelta(days=i)).isoformat(),
             "team1": clubs[i % 6], "team2": clubs[(i + 1) % 6],
             "score": {"ft": [i % 3, (i+1) % 3]}}
            for i in range(120)
        ]
        self.doc = {"name": "Japan | J1 League 2025",
                    "matches": copy.deepcopy(self.matches)}

    def test_date_only_2025_replay_never_promotes_live_japan_bets(self):
        res = evaluate(self.doc, "a" * 64)
        self.assertEqual(res["status"], "RESEARCH_ONLY")
        self.assertEqual(res["finished_score_rows"], 120)
        self.assertEqual(res["source_schedule_rows"], 120)
        self.assertGreater(res["retrospective_evaluated_predictions"], 50)
        self.assertEqual(res["calendar_year_archived"], 2025)
        self.assertEqual(res["official_current_season"], "2026-27")
        self.assertTrue(res["transition_tournament_not_merged"])
        self.assertFalse(res["source_contains_authentic_asof_forecast_snapshots"])
        self.assertFalse(res["development_and_untouched_holdout_seasons_available"])
        self.assertFalse(res["model_calibrated_for_2026_27"])
        self.assertEqual(res["bet_recommendation_count"], 0)
        self.assertEqual(res["production_recommendations"], "DISABLED")
        self.assertIsNone(res["betting_roi_estimate"])

    def test_missing_2025_results_not_counted_as_finished(self):
        for i in range(30):
            self.doc["matches"][i]["score"] = {"ft": None}
        out = evaluate(self.doc, "a" * 64)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["reason"], "J1_HISTORY_TOO_INCOMPLETE_ValueError")

    def test_transition_2026_scores_must_not_mix_in_2025_league(self):
        self.doc["matches"][-1]["date"] = "2026-04-01"
        out = evaluate(self.doc, "a" * 64)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["reason"], "FOREIGN_SEASON_IN_J1_TRAINING_DATA")

    def test_malformed_source_refused(self):
        self.assertEqual(evaluate(None, "a" * 64)["status"], "HOLD")
        self.assertEqual(evaluate(self.doc, "invalid")["status"], "HOLD")
        self.assertEqual(evaluate(self.doc, "a" * 64)["market_comparison_available"], False)

    def test_partial_archive_never_claims_full_historical_coverage(self):
        for i in range(120):
            self.doc["matches"].append({
                "date": (date(2025, 8, 1)+timedelta(days=i)).isoformat(),
                "team1": "Cerezo Osaka", "team2": "Gamba Osaka",
                "score": None,
            })
        out = evaluate(self.doc, "b" * 64)
        self.assertEqual(out["finished_score_rows"], 120)
        self.assertEqual(out["source_schedule_rows"], 240)
        self.assertEqual(out["finished_score_coverage"], .5)
        self.assertFalse(out["forward_betting_win_rate_verified"])


if __name__ == "__main__":
    unittest.main()
