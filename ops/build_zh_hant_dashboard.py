"""將現有機器報告輸出成手機可讀繁體中文靜態頁面（不連網）。"""
import argparse
import html
import json
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


def build_page(readiness=None, shadow=None, market=None):
    sections = [
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
    p.add_argument("--output", required=True)
    args = p.parse_args()

    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8")) if path else None

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_page(read(args.readiness), read(args.shadow),
                                 read(args.market)), encoding="utf-8")
    print(json.dumps({"status": "GENERATED", "output": str(output),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
