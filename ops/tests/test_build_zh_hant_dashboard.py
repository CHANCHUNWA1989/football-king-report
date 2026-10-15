import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_zh_hant_dashboard import build_page


class DashboardTests(unittest.TestCase):
    def test_mobile_traditional_chinese_and_disabled(self):
        page = build_page()
        self.assertIn('lang="zh-Hant-HK"', page)
        self.assertIn('name="viewport"', page)
        self.assertIn("正式推薦：未開放", page)
        self.assertIn("暫無數據", page)

    def test_escape_untrusted_report_fields(self):
        page = build_page(market={"league": "<script>alert(1)</script>"})
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)


if __name__ == "__main__":
    unittest.main()
