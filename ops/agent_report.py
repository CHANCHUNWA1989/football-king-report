"""Render a compact mobile-readable HTML view of the read-only agent audit."""
import argparse
import html
import json
from pathlib import Path

def render(report):
    status = str(report.get("status", "HOLD"))
    sources = report.get("sources", [])
    rows = "".join(
        "<tr><td>" + html.escape(str(s.get("path", ""))) + "</td><td>" +
        html.escape(str(s.get("status", "HOLD"))) + "</td><td>" +
        html.escape(str(s.get("reason") or "—")) + "</td></tr>"
        for s in sources if isinstance(s, dict)
    )
    progress = report.get("six_pillar_progress") or {}
    settlement = progress.get("settlement") or {}
    coverage = progress.get("provider_coverage") or {}
    diagnostics = report.get("diagnostics") or []
    diagnostic_html = "".join("<li>" + html.escape(str(d.get("component", ""))) + ": " +
                              html.escape(str(d.get("reason", ""))) + "</li>"
                              for d in diagnostics if isinstance(d, dict))
    progress_html = ("<h2>六大更新進度</h2><p>可用免費來源：" +
                     html.escape(str(coverage.get("usable_provider_count", "未核實"))) +
                     "｜來源抽樣賽事（可能重疊）：" +
                     html.escape(str(coverage.get("sampled_fixture_total", "未核實"))) +
                     "</p><p>結算樣本：" +
                     html.escape(str(settlement.get("observations", "未核實"))) +
                     "｜距離1000場：" +
                     html.escape(str(progress.get("remaining_to_target", "未核實"))) +
                     "</p><p>結算資料狀態：" + html.escape(str(settlement.get("status", "HOLD"))) +
                     "｜最後檢查：" + html.escape(str(settlement.get("checked_utc", "未核實"))) +
                     "｜資料年齡（小時）：" + html.escape(str(settlement.get("evidence_age_hours", "未核實"))) +
                     "</p><p>獨立驗證賽果：" +
                     html.escape(str(settlement.get("independently_verified_observations", 0))) +
                     "｜端到端運行：" + ("已驗證" if progress.get("end_to_end_workflow_verified") is True else "未驗證") +
                     "</p>")
    return ("<!doctype html><html lang='zh-Hant'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>足球王者 Agent 審核</title><style>"
            "body{font:16px system-ui;max-width:760px;margin:auto;padding:20px;line-height:1.6}"
            "table{width:100%;border-collapse:collapse;overflow-wrap:anywhere}"
            "td,th{padding:9px;border-bottom:1px solid #ddd;text-align:left}"
            "</style><h1>足球王者 AI Agent</h1><p>模式：Shadow Mode（唯讀）</p>"
            "<p>狀態：" + html.escape(status) + "</p>"
            "<p>檢查時間：" + html.escape(str(report.get("checked_at_utc", ""))) + "</p>"
            "<table><thead><tr><th>資料來源</th><th>狀態</th><th>原因</th></tr></thead>"
            "<tbody>" + rows + "</tbody></table>"
            + progress_html + ("<h2>待處理問題</h2><ul>" + diagnostic_html + "</ul>" if diagnostic_html else "") + "<p>下一步：" + html.escape(str(report.get("next_action", "REFRESH_OR_REPAIR_INPUTS"))) + "</p>"
            "<p>正式推薦：停用｜自動投注：停用</p>"
            "<p>注意：資料檢查通過不代表預測準確或可以下注。</p></html>")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(report), encoding="utf-8")

if __name__ == "__main__":
    main()
