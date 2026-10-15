"""將現有機器報告輸出成手機可讀繁體中文靜態頁面（不連網）。"""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from report_zh_hant import readiness_zh, shadow_zh, market_audit_zh


def render_section(title, report):
    rows = []
    for key, value in report.items():
        if key in ("報告", "提示"):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, indent=2)
        elif value is None:
            value = "暫無數據"
        rows.append(f"<dt>{html.escape(str(key))}</dt><dd>{html.escape(str(value))}</dd>")
    return (f"<section><h2>{html.escape(title)}</h2><dl>"
            + "".join(rows) + "</dl><p class='note'>"
            + html.escape(report.get("提示", "")) + "</p></section>")


def existing_sources_zh(consensus=None, summary=None, gates=None):
    consensus, summary, gates = consensus or {}, summary or {}, gates or {}
    progress = summary.get("evidence_progress") or {}
    quota = consensus.get("quota") or {}
    checks = gates.get("checks") or []
    markets = consensus.get("requested_markets") or [consensus.get("market", "未知")]
    timestamp = consensus.get("as_of_utc")
    freshness = "未知（沒有有效快照時間）"
    if isinstance(timestamp, str):
        try:
            captured = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if captured.tzinfo is not None:
                hours = (datetime.now(timezone.utc) - captured).total_seconds() / 3600
                if hours < -0.083333:
                    freshness = "異常：快照時間晚於現在"
                elif hours > 24:
                    freshness = "過期：超過24小時"
                else:
                    freshness = "24小時內快照（不代表即時盤口）"
        except ValueError:
            pass
    return {
        "報告": "足球王者｜現有研究快照",
        "資料時效": freshness,
        "盤口快照時間（UTC）": consensus.get("as_of_utc"),
        "市場賽事數量": consensus.get("event_count"),
        "已請求市場": "、".join(str(x) for x in markets),
        "免費額度餘額（快照）": quota.get("remaining"),
        "封存結算候選個案": progress.get("settled_cases_in_archive"),
        "結算個案目標": progress.get("settled_cases_required"),
        "獨立核實賽果": progress.get("independently_verified_result_cases"),
        "七項品質關卡通過": str(gates.get("passed", "未知")) + "/" + str(gates.get("total", "未知")),
        "未通過關卡": [x.get("key", "未知") for x in checks if isinstance(x, dict) and x.get("state") != "PASS"],
        "正式推薦": "未開放",
        "提示": "以上只係儲存庫內快照，可能過期；市場共識並非獨立模型預測。",
    }


def build_page(readiness=None, shadow=None, market=None, consensus=None, summary=None, gates=None):
    sections = [
        render_section("現有數據及驗收進度", existing_sources_zh(consensus, summary, gates)),
        render_section("正式推薦驗收", readiness_zh(readiness or {})),
        render_section("獨贏盤賽後覆盤", shadow_zh(shadow or {})),
        render_section("三市場盤口品質", market_audit_zh(market or {})),
    ]
    return """<!doctype html>
<html lang="zh-Hant-HK"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>足球王者｜研究報告</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,sans-serif}
body{max-width:860px;margin:auto;padding:18px;line-height:1.65}
header{border-bottom:2px solid #888;padding-bottom:12px}
section{border:1px solid #8886;border-radius:12px;padding:16px;margin:18px 0}
dl{display:grid;grid-template-columns:minmax(120px,1fr) 2fr;gap:9px}
dt{font-weight:700}dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.note{opacity:.85}strong{font-weight:800}
@media(max-width:550px){dl{grid-template-columns:1fr}dd{padding-bottom:8px}}
</style></head><body><header><h1>足球王者｜繁體中文研究報告</h1>
<p><strong>正式推薦：未開放</strong> · 僅供研究，並非投注建議</p></header>
""" + "".join(sections) + "</body></html>"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--readiness")
    p.add_argument("--shadow")
    p.add_argument("--market")
    p.add_argument("--consensus")
    p.add_argument("--summary")
    p.add_argument("--gates")
    p.add_argument("--output", required=True)
    args = p.parse_args()

    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_page(read(args.readiness), read(args.shadow),
                                 read(args.market), read(args.consensus),
                                 read(args.summary), read(args.gates)), encoding="utf-8")
    print(json.dumps({"status": "GENERATED", "output": str(output),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
