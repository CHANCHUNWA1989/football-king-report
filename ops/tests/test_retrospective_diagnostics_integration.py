"""The existing date replay must expose auditable errors without leaking labels."""
import copy
import hashlib
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_backtest import build, parse_archive, replay
from retrospective_stability import audit as stability_audit


def synthetic_document(year):
    clubs = ["A", "B", "C", "D", "E", "F"]
    return {"matches": [{
        "date": (date(year, 8, 1) + timedelta(days=i // 2)).isoformat(),
        "team1": clubs[i % 6], "team2": clubs[(i + 1) % 6],
        "score": {"ft": [i % 4, (i + 1) % 3]},
    } for i in range(240)]}


class RetrospectiveDiagnosticIntegrationTests(unittest.TestCase):
    def test_replay_retains_trace_without_inventing_provider_or_prediction_proof(self):
        matches, _ = parse_archive(synthetic_document(2025))
        rows, _ = replay(matches, "epl", "2025-26")
        self.assertGreater(len(rows), 100)
        self.assertEqual(len({r["replay_case_id"] for r in rows}), len(rows))
        for row in rows:
            self.assertEqual(row["replay_case_id_kind"],
                             "DERIVED_LOCAL_REPLAY_NOT_PROVIDER_NATIVE")
            self.assertLess(row["training_cutoff_local_day"], row["date"])
            self.assertEqual(len(row["training_observations_sha256"]), 64)
            self.assertTrue(row["home"] and row["away"])
            self.assertNotIn("prediction_utc", row)
            self.assertNotIn("kickoff_utc", row)

    def test_same_day_and_future_labels_do_not_change_predictions_or_training_hash(self):
        matches, _ = parse_archive(synthetic_document(2025))
        first, _ = replay(matches, "epl", "2025-26")
        cutoff = date(2025, 10, 10)
        changed = copy.deepcopy(matches)
        for row in changed:
            if row["date"] >= cutoff:
                row["score_ft"] = [20, 0]
        second, _ = replay(changed, "epl", "2025-26")
        def before_or_on(rows):
            return [(r["replay_case_id"], r["original"], r["league_frequency"],
                     r["training_games"], r["training_observations_sha256"])
                    for r in rows if r["date"] <= cutoff.isoformat()]
        self.assertEqual(before_or_on(first), before_or_on(second))

    def test_diagnostics_reach_existing_global_league_json_and_stability_consumer(self):
        docs = {}
        for season, year in (("2024-25", 2024), ("2025-26", 2025)):
            document = synthetic_document(year)
            docs[(season, "epl")] = (document, hashlib.sha256(
                json.dumps(document).encode()).hexdigest())
        before = copy.deepcopy(docs)
        report = json.loads(json.dumps(build(docs), allow_nan=False))
        self.assertEqual(docs, before)
        for season in ("2024-25", "2025-26"):
            for scope in (report["cohorts"][season],
                          report["by_league"]["epl"][season]["statistics"]):
                diagnostic = scope["error_diagnostics"]
                self.assertEqual(diagnostic["n"], scope["n"])
                for key in ("original", "league_frequency"):
                    model = diagnostic["models"][key]
                    matrix = model["confusion_matrix_actual_rows_predicted_columns"]
                    self.assertEqual(sum(map(sum, matrix)), scope["n"])
                    self.assertEqual(sum(matrix[i][i] for i in range(3)),
                                     scope[key]["hits"])
                    self.assertEqual(sum(x["n"] for x in model["top_choice_confidence_bins"]),
                                     scope["n"])
        self.assertTrue(report["holdout_has_already_been_inspected_previously"])
        self.assertFalse(report["live_point_in_time_forecasts_verified"])
        self.assertFalse(report["automatic_model_promotion"])
        self.assertFalse(report["market_baseline_available"])
        self.assertFalse(report["betting_roi_estimable"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        stable = stability_audit(report)
        self.assertEqual(stable["status"], "RESEARCH_ONLY")
        self.assertEqual(stable["league_count"], 1)
        self.assertFalse(stable["can_generate_bet_recommendations"])


if __name__ == "__main__":
    unittest.main()
