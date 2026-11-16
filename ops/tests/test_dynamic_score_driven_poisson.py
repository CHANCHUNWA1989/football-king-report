import copy
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

from ops.dynamic_score_driven_poisson import (
    MODEL_ID, score_grid, predict_offline, date_only_diagnostic_rates, main,
)
from ops.tests.test_penaltyblog_time_decay_research import fixture as penalty_fixture


def fixture():
    p = penalty_fixture()
    p.pop("model")
    p["schema"] = "football-king-dynamic-score-poisson-offline-v1"
    return p


class DynamicScoreDrivenTests(unittest.TestCase):
    def test_offline_actual_score_driven_updates_and_all_market_mass(self):
        p = fixture()
        unmodified = copy.deepcopy(p)
        result = predict_offline(p)
        self.assertEqual(p, unmodified)
        self.assertEqual(result["reason"], "UNVERIFIED_DYNAMIC_POISSON_RESEARCH_ONLY")
        self.assertEqual(result["model_id"], MODEL_ID)
        self.assertEqual(result["training_match_count"], 40)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["source_authenticity_verified"])
        self.assertFalse(result["model_promoted"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertAlmostEqual(sum(result["p_home_draw_away"]), 1, places=9)
        for market in ("over_total_goals_settlement", "home_asian_handicap_settlement"):
            self.assertTrue(result[market])
            for levels in result[market].values():
                self.assertAlmostEqual(sum(levels.values()), 1, places=8)
        self.assertIn("2.75", result["over_total_goals_settlement"])
        self.assertIn("-0.25", result["home_asian_handicap_settlement"])

    def test_new_last_observation_moves_team_strength(self):
        a = fixture()
        b = copy.deepcopy(a)
        # Latest match: d home, a away. A's next-match attacking estimate
        # should respond to new goals involving a, unlike a static rate.
        a["historical_matches"][-1]["away_goals"] = 0
        b["historical_matches"][-1]["away_goals"] = 7
        rates_a = predict_offline(a)
        rates_b = predict_offline(b)
        self.assertEqual(rates_b["status"], "HOLD")
        self.assertGreater(
            rates_b["expected_home_goals"], rates_a["expected_home_goals"])

    def test_future_result_never_trains_model(self):
        data = fixture()
        data["historical_matches"][-1]["result_recorded_utc"] = data["as_of_utc"]
        result = predict_offline(data)
        self.assertEqual(result["reason"], "INVALID_OR_UNAVAILABLE_DYNAMIC_MODEL_HISTORY")
        self.assertNotIn("p_home_draw_away", result)

    def test_source_identity_or_duplicate_rejected(self):
        for change in ("league", "team", "duplicate", "score"):
            data = fixture()
            if change == "league":
                data["historical_matches"][0]["league_id"] = "another-league"
            elif change == "team":
                data["target_fixture"]["home_team_id"] = "brand_new_untrained"
            elif change == "duplicate":
                data["historical_matches"][-1]["event_id"] = data[
                    "historical_matches"][0]["event_id"]
            else:
                data["historical_matches"][0]["home_goals"] = True
            with self.subTest(change=change):
                self.assertEqual(predict_offline(data)["status"], "HOLD")
                self.assertNotIn("expected_home_goals", predict_offline(data))

    def test_invalid_live_contract_never_promotes(self):
        p = fixture()
        p["production_recommendations"] = "ENABLED"
        result = predict_offline(p)
        self.assertEqual(result["reason"], "INVALID_RESEARCH_CONTRACT")
        self.assertFalse(result["positive_ev_verified"])

    def test_date_only_research_fits_only_prior_year_scores(self):
        p = fixture()
        rows = [{
            "date": row["kickoff_utc"][:10],
            "home": row["home_team_id"],
            "away": row["away_team_id"],
            "score_ft": [row["home_goals"], row["away_goals"]],
        } for row in p["historical_matches"]]
        h, a = date_only_diagnostic_rates(rows, "a", "b", date(2026, 5, 1))
        self.assertGreater(h, 0)
        self.assertGreater(a, 0)
        self.assertLess(h, 6.51)
        self.assertLess(a, 6.51)
        rows[-1]["date"] = "2026-05-01"
        with self.assertRaisesRegex(ValueError, "LOOKAHEAD_IN_DATE_ONLY_REPLAY"):
            date_only_diagnostic_rates(rows, "a", "b", date(2026, 5, 1))

    def test_goal_grid_corner_and_quarter_line_normalization(self):
        for h, a in ((0.08, 0.08), (6.5, 6.5), (4.9, 0.3)):
            report = score_grid(h, a)
            self.assertAlmostEqual(sum(report["p_home_draw_away"]), 1, places=9)
            for market in ("over_total_goals_settlement", "home_asian_handicap_settlement"):
                for grades in report[market].values():
                    self.assertAlmostEqual(sum(grades.values()), 1, places=8)

    def test_duplicate_json_input_fails_before_model(self):
        p = fixture()
        raw = json.dumps(p).replace(
            '"schema": "football-king-dynamic-score-poisson-offline-v1"',
            '"schema": "football-king-dynamic-score-poisson-offline-v1", "schema": "bad"', 1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.json"
            source.write_text(raw, encoding="utf-8")
            with patch("sys.argv", ["dynamic", "--input", str(source)]):
                with redirect_stdout(io.StringIO()), self.assertRaisesRegex(
                        ValueError, "DUPLICATE_JSON_KEY"):
                    main()


if __name__ == "__main__":
    unittest.main()
