import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from report_zh_hant import readiness_zh, shadow_zh


class ChineseReportTests(unittest.TestCase):
    def test_readiness(self):
        result = readiness_zh({"status": "HOLD", "checks": {}})
        self.assertEqual(result["正式推薦"], "未開放")
        self.assertEqual(len(result["檢查項目"]), 5)

    def test_missing_metrics_remain_missing(self):
        result = shadow_zh({"status": "RESEARCH_ONLY", "accepted": 0,
                            "mean_brier": None, "mean_log_loss": None})
        self.assertIsNone(result["平均Brier分數"])
        self.assertEqual(result["正式推薦"], "未開放")


if __name__ == "__main__":
    unittest.main()
