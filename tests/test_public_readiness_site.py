import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path
from ops.public_readiness_site import build, publish, render_section
from ops.private_artifact_guard import sanitize

NOW = datetime(2026, 10, 10, 11, tzinfo=timezone.utc)
SETTLED = {"samples": [{"key": "match1", "league": "bundesliga",
                         "kickoff_utc": "2026-10-09T19:00:00+00:00",
                         "fixture_result_source_independently_verified": False}],
           "n": 1, "production_recommendations": "DISABLED"}
GATES = {"captured_utc": "2026-10-10T08:46:54+00:00",
         "checks": [
             {"key": "model_promotion_safety", "state": "PASS"},
             {"key": "out_of_sample_calibration", "state": "HOLD"},
             {"key": "utc_fixture_identity", "state": "PARTIAL"}]}
MARKET = {"as_of_utc": "2026-10-10T01:21:15+00:00",
          "status": "RESEARCH_ONLY", "event_count": 117}

class PublicReadinessTests(unittest.TestCase):
    def test_conflicting_or_repeated_gate_is_not_a_pass_in_either_order(self):
        for states in (("PASS", "HOLD"), ("HOLD", "PASS"), ("PASS", "PASS")):
            with self.subTest(states=states):
                gates = dict(GATES, checks=[
                    {"key": "model_promotion_safety", "state": s} for s in states])
                result = build(SETTLED, gates, MARKET, NOW)
                self.assertEqual(result["quality_gates_passed"], 0)
                self.assertEqual(result["quality_gates_remaining"], 7)
                self.assertEqual(result["quality_gate_states"]["model_promotion_safety"], "HOLD")
                self.assertEqual(result["official_recommendation_count"], 0)

    def test_complete_unique_gates_and_missing_or_invalid_checks(self):
        from ops.public_readiness_site import EXPECTED_GATE_KEYS
        complete = [{"key": key, "state": "PASS"} for key in EXPECTED_GATE_KEYS]
        result = build(SETTLED, dict(GATES, checks=complete), MARKET, NOW)
        self.assertEqual(result["quality_gates_passed"], 7)
        self.assertEqual(result["quality_gates_remaining"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        for invalid in (None, {}, [], [True, None, {"key": "invented", "state": "PASS"}],
                        [{"key": "model_promotion_safety", "state": True}]):
            with self.subTest(checks=invalid):
                result = build(SETTLED, dict(GATES, checks=invalid), MARKET, NOW)
                self.assertEqual(result["quality_gates_passed"], 0)
                self.assertEqual(result["quality_gates_remaining"], 7)

    def test_unfinished_quality_count_and_each_gate_are_visible(self):
        result = build(SETTLED, GATES, MARKET, NOW)
        self.assertEqual(result["quality_gates_remaining"], 6)
        self.assertEqual(len(result["quality_gate_states"]), 7)
        markup = render_section(result)
        self.assertIn("尚有6項品質檢查未達標", markup)
        self.assertIn("賽事身份及開波時間：部分完成", markup)
        self.assertIn("樣本外概率校準：未達標或資料不足", markup)
        self.assertIn("模型升級保護：通過", markup)

    def test_renderer_uses_gate_states_instead_of_forged_aggregate_counts(self):
        result = build(SETTLED, GATES, MARKET, NOW)
        result.update(quality_gates_passed=7, quality_gates_remaining=0)
        markup = render_section(result)
        self.assertIn("檢查通過 1/7", markup)
        self.assertIn("尚有6項品質檢查未達標", markup)
        for invalid in (None, [], True):
            result["quality_gate_states"] = invalid
            markup = render_section(result)
            self.assertIn("檢查通過 0/7", markup)
            self.assertIn("尚有7項品質檢查未達標", markup)

    def test_forged_row_claims_do_not_reduce_authenticated_deficit(self):
        settled = {"samples": [dict(SETTLED["samples"][0],
                                   fixture_result_source_independently_verified=True)]}
        result = build(settled, GATES, MARKET, NOW)
        self.assertEqual(result["result_rows_marked_independently_verified"], 1)
        self.assertEqual(result["independently_verified_result_cases"], 0)
        self.assertEqual(result["remaining_authenticated_forward_settlements"], 300)
        self.assertEqual(result["still_needed_if_existing_rows_pass_independent_audit"], 299)
        markup = render_section(result)
        self.assertIn("已認證獨立賽果 0/300 場", markup)
        self.assertIn("仍欠已認證樣本 300 場", markup)
        self.assertIn("來源自行標示 1 場（未認證）", markup)
        self.assertNotIn("獨立核實 1/300", markup)

    def test_public_view_keeps_all_three_hundred_claims_distinct(self):
        descriptive = {
            "settled_cases_in_archive": 300,
            "result_rows_marked_independently_verified": 300,
            "independently_verified_result_cases": 0,
            "independent_week_blocks": 12,
            "leagues_with_40_settlements": 4}
        with patch("ops.public_readiness_site.grounded_progress", return_value=descriptive):
            result = build(SETTLED, GATES, MARKET, NOW)
        self.assertEqual(result["result_rows_marked_independently_verified"], 300)
        self.assertEqual(result["still_needed_if_existing_rows_pass_independent_audit"], 0)
        self.assertEqual(result["remaining_authenticated_forward_settlements"], 300)
        markup = render_section(result)
        self.assertIn("已認證獨立賽果 0/300 場", markup)
        self.assertIn("來源自行標示 300 場（未認證）", markup)
        self.assertIn("已記錄 12 個週次", markup)
        self.assertIn("不等於合資格週次", markup)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_renderer_does_not_treat_report_counters_as_admitted_proof(self):
        result = build(SETTLED, GATES, MARKET, NOW)
        result.update(independently_verified_result_cases=300,
                      remaining_authenticated_forward_settlements=0,
                      required_independently_verified_cases=1)
        markup = render_section(result)
        self.assertIn("已認證獨立賽果 0/300 場", markup)
        self.assertIn("仍欠已認證樣本 300 場", markup)
        self.assertNotIn("已認證獨立賽果 300", markup)

    def test_real_evidence_shows_gap_not_fake_completion(self):
        result = build(SETTLED, GATES, MARKET, NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["quality_gates_passed"], 1)
        self.assertEqual(result["recorded_settled_cases"], 1)
        self.assertEqual(result["result_rows_marked_independently_verified"], 0)
        self.assertEqual(result["still_needed_if_existing_rows_pass_independent_audit"], 300)
        self.assertFalse(result["actual_bettable_odds_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("decimal_odds", json.dumps(result))

    def test_live_private_api_coverage_visible_without_raw_bookmaker_prices(self):
        private = sanitize({
            "input_status": "CONNECTED",
            "generated_utc": NOW.isoformat(),
            "counts": {"RESEARCH_ONLY": 3837},
            "coverage": [{"league": "epl", "quotes": 1200,
                          "decimal_odds": 2.40, "home": "NEVER-EXPOSE"}],
            "requested_markets": ["h2h"]},
            {"grounded_progress": {"settled_cases_in_archive": 1}})
        report = build(SETTLED, GATES, MARKET, NOW, private)
        self.assertEqual(report["private_quote_collector_status"], "CONNECTED")
        self.assertEqual(report["private_h2h_research_quote_count"], 3837)
        self.assertEqual(report["official_recommendation_count"], 0)
        html = render_section(report)
        self.assertIn("3837", html)
        self.assertNotIn("NEVER-EXPOSE", html)
        self.assertNotIn("2.40", html)
        private["bookmaker"] = "illegal-book"
        self.assertEqual(build(SETTLED, GATES, MARKET, NOW, private)["private_quote_collector_status"],
                         "INVALID_OR_STALE")

    def test_old_private_quote_coverage_is_not_realtime(self):
        private = sanitize({
            "input_status": "CONNECTED",
            "generated_utc": "2026-10-09T00:00:00+00:00",
            "counts": {"RESEARCH_ONLY": 3837},
            "coverage": [], "requested_markets": ["h2h"]},
            {"grounded_progress": {}})
        report = build(SETTLED, GATES, MARKET, NOW, private)
        self.assertEqual(report["private_quote_collector_status"], "STALE")
        self.assertEqual(report["private_h2h_research_quote_count"], 0)

    def test_rejects_stale_market_and_quality(self):
        result = build(SETTLED, GATES, MARKET,
                       datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertFalse(result["market_baseline_fresh"])
        self.assertFalse(result["quality_fresh"])
        self.assertEqual(result["market_baseline_event_count"], 0)

    def test_no_untrusted_html_or_raw_quotes(self):
        progress = build(SETTLED, GATES, MARKET, NOW)
        markup = render_section(progress)
        self.assertIn('id="fk-official-readiness"', markup)
        self.assertIn("HOLD", markup)
        self.assertNotIn("bookmaker", markup)
        self.assertNotIn("3.75", markup)

    def test_end_to_end_publication_without_raw_data(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            site = p / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<html><main><h2>近期賽程與賽果</h2></main></html>",
                encoding="utf-8")
            for n, payload in (("settled.json", SETTLED),
                               ("gates.json", GATES), ("market.json", MARKET)):
                (p / n).write_text(json.dumps(payload), encoding="utf-8")
            report = publish(site, p / "settled.json", p / "gates.json",
                             p / "market.json", now=NOW)
            result = json.loads((site / "official_readiness.json").read_text())
            self.assertEqual(result, report)
            html = (site / "index.html").read_text()
            self.assertEqual(html.count('id="fk-official-readiness"'), 1)
            with self.assertRaises(ValueError):
                publish(site, p / "settled.json", p / "gates.json",
                        p / "market.json", now=NOW)

if __name__ == "__main__":
    unittest.main()
