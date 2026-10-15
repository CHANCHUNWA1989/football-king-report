"""足球王者繁體中文報告顯示層；保留英文機器欄位以免破壞 API。"""

STATUS = {
    "HOLD": "暫停：資料或驗證不足",
    "RESEARCH_ONLY": "研究模式：不可當作正式推薦",
    "EVIDENCE_REVIEW": "證據待人工審查",
    "DRY_RUN": "零額度模擬測試",
}
CHECKS = {
    "verified_complete_three_market_quotes": "已核實獨贏、亞洲讓球及大小球完整盤口",
    "independent_pre_match_forecasts": "有開賽前獨立模型預測",
    "settled_out_of_sample_validation": "已完成賽後樣本外驗證",
    "calibration_and_leakage_review": "已檢查概率校準及資料洩漏",
    "human_approval": "已取得人工審批",
}


def readiness_zh(report):
    checks = report.get("checks", {})
    return {
        "報告": "足球王者｜正式推薦驗收",
        "狀態": STATUS.get(report.get("status"), "未知狀態"),
        "檢查項目": [
            {"項目": label, "結果": "通過" if checks.get(key) is True else "未通過"}
            for key, label in CHECKS.items()
        ],
        "正式推薦": "未開放",
        "提示": "檢查結果只反映輸入證據標記，並非獨立核實證據真確。",
    }


def shadow_zh(report):
    return {
        "報告": "足球王者｜獨贏盤賽後覆盤",
        "狀態": STATUS.get(report.get("status"), "未知狀態"),
        "有效賽事": report.get("accepted", 0),
        "排除賽事": report.get("rejected", 0),
        "平均Brier分數": report.get("mean_brier"),
        "平均對數損失": report.get("mean_log_loss"),
        "最高概率方向命中率": report.get("top_probability_accuracy"),
        "千場樣本門檻": "達到" if report.get("minimum_sample_for_skill_claim_met") is True else "未達到",
        "正式推薦": "未開放",
        "提示": "命中率與評分並不等於盈利；未完成獨立市場基準比較。",
    }

MARKETS_ZH = {"h2h": "獨贏（主勝／和局／客勝）",
              "spreads": "亞洲讓球", "totals": "入球大小"}
REASONS_ZH = {
    "QUOTA_RESERVE": "免費 API 額度不足，暫停採集",
    "FREE_QUOTA_GUARD": "已觸發免費額度保護",
    "MISSING_KEY": "未設定 API 金鑰",
    "MISSING_QUOTA_HEADERS": "供應商未提供可靠額度資料",
    "LEAGUE_UNAVAILABLE": "聯賽目前不可用",
    "MISMATCHED_SPORT": "資料所屬聯賽不符",
    "NO_VALID_3WAY_MARKET_SNAPSHOTS": "未有可用嘅完整獨贏盤快照",
}


def market_audit_zh(report):
    counts = report.get("complete_prematch_bookmaker_lines_by_market", {})
    missing = report.get("missing_markets", [])
    return {
        "報告": "足球王者｜三市場盤口品質",
        "狀態": STATUS.get(report.get("status"), "暫停或未知狀態"),
        "聯賽": report.get("league", "未提供"),
        "完整賽前盤口數量": {
            label: counts.get(key, 0) for key, label in MARKETS_ZH.items()
        },
        "缺少市場": [MARKETS_ZH.get(key, key) for key in missing],
        "暫停原因": REASONS_ZH.get(report.get("reason"), report.get("reason")),
        "正式推薦": "未開放",
        "提示": "完整盤口數量不代表模型有預測優勢，亦不代表可投注。",
    }
