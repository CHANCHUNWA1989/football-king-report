import sys
import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_zh_hant_dashboard import build_page, existing_sources_zh, main


class DashboardTests(unittest.TestCase):
    @staticmethod
    def case_replay_fixture():
        false_flags = {
            "forecast_sealed_pre_match": False,
            "offered_market_authenticated": False,
            "calibration_verified": False,
            "results_independently_verified": False,
            "positive_ev_verified": False,
        }
        scorelines = [
            {"home_goals": h, "away_goals": a, "probability": p}
            for h, a, p in ((1, 0, .30), (1, 1, .20), (2, 0, .15),
                            (2, 1, .10), (0, 0, .05))
        ]
        scoring = {
            "schema": "football-king-case-goal-market-reconstruction-v1",
            "status": "HOLD", "production_recommendations": "DISABLED",
            "candidate_only": True, "certified_case_count": 0,
            "derived_reconstruction": True, "derived_review_not_a_trust_input": True,
            "distribution_sealed_pre_match": False, "independently_verified": False,
            "eligible_for_model_scoring": False, "eligible_for_betting_promotion": False,
            "results_independently_verified": False,
            "offered_handicap_line_authenticated": False,
            "offered_totals_line_authenticated": False,
            "offered_decimal_odds_authenticated": False,
            "probability_calibration_verified": False,
            "positive_expected_value_verified": False,
            "both_teams_to_score": {
                **false_flags, "status": "HOLD", "production_recommendations": "DISABLED",
                "basis": "DERIVED_INDEPENDENT_POISSON_GRID",
                "probabilities": {"YES": .55, "NO": .45},
            },
            "correct_score_diagnostic": {
                **false_flags, "status": "HOLD", "production_recommendations": "DISABLED",
                "basis": "DERIVED_INDEPENDENT_POISSON_GRID", "top_k": 5,
                "top_scorelines": scorelines,
                "top_scorelines_probability_mass": .80,
                "other_in_grid_probability_mass": .20,
            },
            "result_market_diagnostics": {
                **false_flags, "status": "HOLD", "production_recommendations": "DISABLED",
                "basis": "DERIVED_INDEPENDENT_POISSON_GRID",
                "double_chance": {"1X": .85, "X2": .65, "12": .50},
                "double_chance_markets_overlap": True,
                "draw_no_bet": {
                    "HOME": {"full_win_probability": .60, "push_probability": .20,
                             "full_loss_probability": .20,
                             "conditional_win_probability_given_no_push": .75},
                    "AWAY": {"full_win_probability": .20, "push_probability": .20,
                             "full_loss_probability": .60,
                             "conditional_win_probability_given_no_push": .25},
                },
            },
        }
        return {
            "schema": "football-king-controlled-case-replay-v1",
            "status": "HOLD", "production_recommendations": "DISABLED",
            "replay_completed": True, "candidate_only": True,
            "derived_review_not_a_trust_input": True,
            "goal_market_replay_completed": True,
            "goal_market_scoring": scoring,
        }

    def test_claimed_aggregate_and_duplicates_cannot_hide_unfinished_gates(self):
        for checks in ([], [{"state": "PASS"}] * 7,
                       [{"key": "model_promotion_safety", "state": "PASS"},
                        {"key": "model_promotion_safety", "state": "HOLD"}]):
            with self.subTest(checks=checks):
                result = existing_sources_zh(gates={"passed": 7, "total": 7, "checks": checks})
                self.assertEqual(result["七項品質關卡通過"], "0/7")
                self.assertEqual(len(result["未通過關卡"]), 7)
                self.assertEqual(result["正式推薦"], "未開放")

    def test_mobile_traditional_chinese_and_disabled(self):
        page = build_page()
        self.assertIn('lang="zh-Hant-HK"', page)
        self.assertIn('name="viewport"', page)
        self.assertIn("正式推薦：未開放", page)
        self.assertIn("暫無數據", page)

    def test_case_replay_renders_safe_research_probability_cards(self):
        page = build_page(case_replay=self.case_replay_fixture())
        self.assertIn("衍生研究概率", page)
        self.assertIn("雙方入球", page)
        self.assertIn("候選比分 Top 5", page)
        self.assertIn("其餘保留比分格", page)
        self.assertIn("雙重機會（互相重疊）", page)
        self.assertIn("和局退款（DNB）", page)
        self.assertIn("重疊概率總和為 2", page)
        self.assertIn("role='progressbar'", page)
        self.assertIn("正式推薦：HOLD／DISABLED", page)
        self.assertIn("非賽前封存、非可成交報價、未校準、未獨立核實，亦非 EV", page)

    def test_invalid_case_replay_fails_closed_without_probability_values(self):
        report = self.case_replay_fixture()
        report["goal_market_scoring"]["both_teams_to_score"]["probabilities"]["YES"] = True
        page = build_page(case_replay=report)
        self.assertIn("研究概率資料未能通過格式及安全驗證", page)
        self.assertNotIn("55.0%", page)
        self.assertNotIn("候選比分 Top 5", page)
        self.assertIn("正式推薦：HOLD／DISABLED", page)

    def test_invalid_safety_flags_hide_all_case_probabilities(self):
        report = self.case_replay_fixture()
        report["goal_market_scoring"]["result_market_diagnostics"]["positive_ev_verified"] = True
        page = build_page(case_replay=report)
        self.assertIn("研究概率資料未能通過格式及安全驗證", page)
        self.assertNotIn("和局退款（DNB）", page)

    def test_case_replay_input_is_not_mutated(self):
        report = self.case_replay_fixture()
        before = copy.deepcopy(report)
        build_page(case_replay=report)
        self.assertEqual(report, before)

    def test_cli_refuses_to_overwrite_case_replay_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "case.json"
            original = json.dumps(self.case_replay_fixture()).encode()
            path.write_bytes(original)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(["--case-replay", str(path), "--output", str(path)])
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(path.read_bytes(), original)

    def test_existing_snapshot_evidence_is_visible(self):
        page = build_page(
            consensus={"event_count": 114, "market": "h2h",
                       "as_of_utc": "2026-10-14T13:38:46Z"},
            summary={"evidence_progress": {"settled_cases_in_archive": 28,
                                          "settled_cases_required": 300,
                                          "independently_verified_result_cases": 0}},
            gates={"passed": 1, "total": 7, "checks": [
                {"key": "model_promotion_safety", "state": "PASS"}]})
        self.assertIn("114", page)
        self.assertIn("28", page)
        self.assertIn("1/7", page)
        self.assertIn("正式推薦：未開放", page)

    def test_old_snapshot_explicitly_marked_stale(self):
        page = build_page(consensus={"as_of_utc": "2020-01-01T00:00:00Z"})
        self.assertIn("過期：超過24小時", page)
        self.assertIn("正式推薦：未開放", page)

    def test_future_snapshot_not_treated_as_live(self):
        page = build_page(consensus={"as_of_utc": "2099-01-01T00:00:00Z"})
        self.assertIn("異常：快照時間晚於現在", page)

    def test_escape_untrusted_report_fields(self):
        page = build_page(market={"league": "<script>alert(1)</script>"})
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
