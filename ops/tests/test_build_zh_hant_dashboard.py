import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_zh_hant_dashboard import build_page, existing_sources_zh


class DashboardTests(unittest.TestCase):
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
