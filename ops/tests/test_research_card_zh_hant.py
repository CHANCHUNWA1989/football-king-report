import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_card_zh_hant import render_card

NOW = datetime(2026, 11, 17, 11, 0, tzinfo=timezone.utc)


def sample():
    return {
        "fixture": {"home_id": "team-1", "away_id": "team-2",
                    "home_zh": "測試主隊", "away_zh": "測試客隊",
                    "competition_zh": "示範賽", "kickoff_utc": "2026-11-17T12:00:00Z"},
        "quote": {"bookmaker": "測試公司", "market_zh": "大小球", "selection_zh": "大2.5球",
                  "decimal_odds": 1.88, "updated_utc": "2026-11-17T10:59:20Z",
                  "captured_utc": "2026-11-17T10:59:25Z",
                  "source_url": "https://example.com/synthetic"},
        "models": [{"name": "示範泊松", "probability": 0.545,
                    "forecast_cutoff_utc": "2026-11-17T10:50:00Z"}],
        "tactical_note": "主隊邊路假設，未經驗證",
        "motivation_note": "戰意尚需核實",
    }


class ResearchCardTests(unittest.TestCase):
    def test_valid_structure_is_still_hold_and_is_not_a_pick(self):
        report = render_card(sample(), now=NOW)
        self.assertIn("測試主隊 VS 測試客隊", report)
        self.assertIn("20:00（香港時間）", report)
        self.assertIn("大2.5球", report)
        self.assertIn("1.88", report)
        self.assertIn("54.5%", report)
        self.assertIn("HOLD", report)
        self.assertIn("正式投注推薦：停用", report)
        self.assertIn("正EV：未獲認證", report)
        self.assertNotIn("✅正式推薦", report)

    def test_stale_quote_must_not_be_presented_as_live_price(self):
        payload = sample()
        payload["quote"]["updated_utc"] = "2026-11-17T10:50:00Z"
        report = render_card(payload, now=NOW)
        self.assertIn("過時／未通過", report)
        self.assertNotIn("實時可成交", report)
        self.assertIn("HOLD", report)

    def test_missing_identity_or_post_kickoff_forecast_is_withheld(self):
        payload = sample()
        payload["fixture"]["away_id"] = "team-1"
        payload["models"][0]["forecast_cutoff_utc"] = "2026-11-17T12:01:00Z"
        report = render_card(payload, now=NOW)
        self.assertNotIn("54.5%", report)
        self.assertIn("身份未能確認", report)
        self.assertIn("HOLD", report)

    def test_invalid_odds_are_not_printed_as_prices(self):
        payload = sample()
        payload["quote"]["decimal_odds"] = float("nan")
        report = render_card(payload, now=NOW)
        self.assertNotIn("nan", report.lower())
        self.assertIn("盤口：未提供可核查資料", report)

    def test_higher_price_is_not_a_verified_ev_claim(self):
        payload = sample()
        payload["quote"]["decimal_odds"] = 2.50
        payload["quote"]["independently_verified"] = True
        payload["models"][0]["verified"] = True
        report = render_card(payload, now=NOW)
        self.assertIn("正EV：未獲認證", report)
        self.assertIn("正式投注推薦：停用", report)


if __name__ == '__main__':
    unittest.main()
