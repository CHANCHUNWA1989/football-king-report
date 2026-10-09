"""Fail-closed final publication gate; make status, website and client freshness agree.

Runs after the old V4.1 HTML generator and research audit. Retains original
V4.1 ZIP byte-for-byte, but refuses an incomplete published HTML.
"""
import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_AGE_HOURS = 10
STALE_JS = """(() => {
  'use strict';
  const banner = document.getElementById('research-banner');
  if (!banner) return;
  const checked = Date.parse(banner.dataset.checked || '');
  const age = Date.now() - checked;
  if (!Number.isFinite(checked) || age < -5*60*1000 || age > 10*60*60*1000) {
    banner.textContent = 'HOLD：報告超過10小時未更新，或時間戳異常。請核對雲端運行紀錄。';
    banner.setAttribute('data-live-status', 'HOLD');
    banner.style.color = '#b45309';
  }
})();"""


def _json(path):
    item = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(item, dict):
        raise ValueError("INVALID_PUBLIC_JSON")
    return item


def _utc(text):
    dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_PUBLIC_TIME")
    return dt.astimezone(timezone.utc)


def _section(key, title, details, link):
    return ('<section id="' + key + '" role="status">'
            '<h2>' + html.escape(title) + '</h2>'
            '<p class="small">' + html.escape(details) + '</p>'
            '<p><a href="' + link + '">查看驗證明細（JSON）</a></p></section>')


def finalize(site, now=None):
    site = Path(site)
    report = _json(site / "report.json")
    status = _json(site / "status.json")
    quality = _json(site / "quality.json")
    validation = _json(site / "validation.json")
    shadow = _json(site / "shadow.json")
    source = (site / "index.html").read_text(encoding="utf-8")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    if (report.get("checked_utc") != status.get("checked_utc")
            or status.get("checked_utc") != quality.get("checked_utc")):
        raise ValueError("INCONSISTENT_CAPTURE_TIMES")
    age = (now - _utc(status["checked_utc"])).total_seconds()
    is_stale = age < -300 or age > MAX_AGE_HOURS * 3600
    if any(d.get("production_recommendations") != "DISABLED" for d in (report, status, quality, validation)):
        raise ValueError("RECOMMENDATIONS_MUST_STAY_DISABLED")
    if validation.get("status") != "HOLD":
        raise ValueError("SHADOW_EVIDENCE_CANNOT_AUTHORIZE_PRODUCTION")
    if (shadow.get("production_recommendations") != "DISABLED"
            or shadow.get("status") not in ("SHADOW_ONLY", "HOLD")
            or shadow.get("market_odds_available") is not False
            or shadow.get("model_calibrated") is not False
            or not isinstance(shadow.get("predictions"), list)):
        raise ValueError("INVALID_SHADOW_PROVENANCE_OR_SAFETY")
    if abs((_utc(shadow["as_of_utc"]) - _utc(status["checked_utc"])).total_seconds()) > 1800:
        raise ValueError("SHADOW_AND_FIXTURE_CAPTURE_TOO_FAR_APART")
    if (status.get("quality_status") != quality.get("status")
            or status.get("status") != report.get("status")):
        raise ValueError("INCONSISTENT_RESEARCH_STATUS")
    if status["status"] not in ("HOLD", "RESEARCH_ONLY"):
        raise ValueError("INVALID_REPORT_STATUS")
    errors = quality.get("critical_errors")
    if not isinstance(errors, list):
        raise ValueError("INVALID_QUALITY_SCHEMA")
    safe_status = "HOLD" if (is_stale or errors or status["status"] == "HOLD") else "RESEARCH_ONLY"
    report["status"] = safe_status
    status["status"] = safe_status
    status["freshness_threshold_hours"] = MAX_AGE_HOURS
    if is_stale:
        status["publication_warning"] = "STALE_OR_FUTURE_REPORT"
    if 'id="research-banner"' not in source:
        raise ValueError("MISSING_VISIBLE_SAFETY_BANNER")
    if "正式投注推薦：停用" not in source:
        raise ValueError("MISSING_BETTING_SAFETY_NOTICE")
    source = re.sub(r'(<div\b[^>]*\bid="research-banner"[^>]*>).*?(</div>)',
                    lambda m: m.group(1) +
                        ("HOLD：品質或更新時間未通過，不能用作預測。" if safe_status == "HOLD"
                         else "RESEARCH_ONLY：公開賽程僅供研究，未獨立核實。") + m.group(2),
                    source, count=1, flags=re.S)
    required_sections = [
        ("quality-audit", "資料品質與來源透明度",
         ("品質：" + str(quality["status"]) +
          "；有準確開賽時刻的賽事：" + str(quality.get("matches_with_precise_kickoff", 0)) +
          "/" + str(quality.get("public_matches", 0)) +
          "；上游更新時間及資料真確性尚未獨立驗證。"),
         "quality.json"),
        ("shadow-validation", "預測與市場基準驗證",
         ("狀態：HOLD；已結算且有市場基準的樣本：" +
          str(validation.get("n", 0)) +
          "；原因：" + str(validation.get("reason", "NO_VERIFIED_EVIDENCE")) +
          "。研究概率不得當作投注建議。"),
         "validation.json"),
    ]
    if "</body>" not in source:
        raise ValueError("MISSING_HTML_BODY_END")
    # Explicitly label shadow probabilities as uncalibrated, without betting selections.
    candidates = shadow["predictions"][:15]
    forecast_rows = "".join(
        '<tr><td>' + html.escape(str(m.get("league", ""))) + '</td><td>' +
        html.escape(str(m.get("home", ""))[:100]) + ' — ' +
        html.escape(str(m.get("away", ""))[:100]) + '</td><td>' +
        ' / '.join("%.1f%%" % (100 * float(m.get(k, 0)))
                   for k in ("p_home", "p_draw", "p_away")) + '</td></tr>'
        for m in candidates)
    shadow_panel = ('<section id="shadow-research-only"><h2>賽前影子概率研究（非投注建議）</h2>'
        '<p class="small">候選比賽：' + str(shadow.get("predictions_count", 0)) +
        '。概率未校準，缺乏合法當時市場賠率；嚴禁視作投注建議或預測優勢。</p>' +
        ('<div class="scroll"><table><thead><tr><th>聯賽</th><th>球隊</th>'
         '<th>主勝 / 和局 / 客勝（研究概率）</th></tr></thead><tbody>' +
         forecast_rows + '</tbody></table></div>' if forecast_rows else
         '<p class="small">今次沒有符合訓練量及準確開賽時間條件嘅賽前候選。</p>') +
        '<p><a href="shadow.json">查看影子研究紀錄（JSON）</a></p></section>')
    if 'id="shadow-research-only"' not in source:
        source = source.replace("</body>", shadow_panel + "</body>", 1)
    for key, title, description, link in required_sections:
        if 'id="' + key + '"' not in source:
            source = source.replace("</body>", _section(key, title, description, link) + "</body>", 1)
    for key, _, _, _ in required_sections:
        if source.count('id="' + key + '"') != 1:
            raise ValueError("DUPLICATE_OR_MISSING_SAFETY_SECTION_" + key)
    if source.count('id="shadow-research-only"') != 1:
        raise ValueError("MISSING_SHADOW_RESEARCH_WARNING")
    if 'src="freshness.js"' not in source:
        raise ValueError("MISSING_CLIENT_FRESHNESS_SCRIPT")
    if safe_status == "HOLD" and "HOLD：品質或更新時間未通過" not in source:
        raise ValueError("HOLD_NOT_VISIBLE")
    # These 4 files are generated atomically by the Python runner before Pages upload.
    for name, payload in (("status.json", status), ("report.json", report)):
        (site / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (site / "freshness.js").write_text(STALE_JS + "\n", encoding="utf-8")
    (site / "index.html").write_text(source, encoding="utf-8")
    return {"status": safe_status, "max_age_hours": MAX_AGE_HOURS,
            "quality_section_visible": True, "shadow_section_visible": True,
            "stale": is_stale, "recommendations_disabled": True}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    args = p.parse_args()
    print(json.dumps(finalize(args.site), ensure_ascii=False))
