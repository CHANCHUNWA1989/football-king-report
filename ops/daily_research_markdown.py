"""Human-readable football research report; strictly non-executable."""
def render_markdown(report):
    if report.get("production_recommendations") != "HOLD" or report.get("positive_ev_verified") is not False:
        raise ValueError("UNSAFE_REPORT")
    lines = [
        "# 足球王者｜每日賽前研究報告",
        "",
        f"生成時間 (UTC)：{report['generated_utc']}",
        "",
        "**研究用途，非正式投注推薦。正EV未經驗證；所有投注功能 HOLD。**",
        "",
        f"賽事數量：{report['sample_count']}；可供研究：{report['research_only_count']}",
        "",
    ]
    for card in report["cards"]:
        if card.get("betting_recommendation") != "HOLD" or card.get("positive_ev_verified") is not False:
            raise ValueError("UNSAFE_CARD")
        lines.extend([
            f"## {card['home_team']} vs {card['away_team']}",
            f"- 賽事編號：{card['fixture_id']}",
            f"- 開賽時間 (UTC)：{card['kickoff_utc']}",
            f"- 狀態：{card['status']}（{card['reason']}）",
        ])
        quote = card.get("quote")
        if quote is not None:
            lines.extend([
                f"- 賠率提供方（未獨立核實）：{quote['provider']}",
                f"- 莊家：{quote['bookmaker']}",
                f"- 盤口：{quote['market']} {quote['selection']} {quote['line']:+g}",
                f"- 十進制賠率：{quote['decimal_odds']:g}",
                f"- 報價時間 (UTC)：{quote['quote_utc']}",
                f"- 報價識別碼：{quote['provider_quote_id']}",
                "- 報價真實性／可成交性：未經獨立驗證",
            ])
        else:
            lines.append("- 盤口：無可用報價")
        probability = card.get("model_probability_uncalibrated")
        lines.append("- 模型概率：未提供" if probability is None else
                     f"- 模型概率（未校準）：{probability:.1%}")
        lines.extend(["- 正EV：**未經驗證**", "- 投注建議：**HOLD**", ""])
    if not report["cards"]:
        lines.extend(["沒有賽事輸入；不提供推薦。", ""])
    return "\n".join(lines)
