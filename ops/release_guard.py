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
  function checkFreshness() {
    const checked = Date.parse(banner.dataset.checked || '');
    const age = Date.now() - checked;
    if (!Number.isFinite(checked) || age < -5*60*1000 || age > 10*60*60*1000) {
      banner.textContent = 'HOLD：報告超過10小時未更新，或時間戳異常。請核對雲端運行紀錄。';
      banner.setAttribute('data-live-status', 'HOLD');
      banner.style.color = '#b45309';
    }
  }
  checkFreshness();
  // Mobile Safari may stay open for hours: re-check without needing reload.
  setInterval(checkFreshness, 60*1000);
  document.addEventListener('visibilitychange', checkFreshness);
  window.addEventListener('pageshow', checkFreshness);
  window.addEventListener('focus', checkFreshness);
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
    crosscheck = _json(site / "crosscheck.json")
    market_status = _json(site / "market_status.json")
    market_pairs = _json(site / "market_comparison.json")
    coverage = _json(site / "league_coverage.json")
    ab = _json(site / "ab_status.json")
    center = _json(site / "research_center.json")
    gate = _json(site / "production_gate.json")
    selections = _json(site / "research_selections.json")
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
    if (crosscheck.get("production_recommendations") != "DISABLED"
            or crosscheck.get("status") not in ("CONFLICT", "INCONCLUSIVE", "PARTIAL_CHECK")
            or crosscheck.get("all_leagues_verified") is not False):
        raise ValueError("INVALID_INDEPENDENT_SOURCE_CROSSCHECK")
    if crosscheck.get("score_conflicts", 0) and quality.get("status") != "HOLD":
        raise ValueError("CROSSCHECK_CONFLICT_WITHOUT_QUALITY_HOLD")
    if (market_status.get("production_recommendations") != "DISABLED"
            or market_pairs.get("production_recommendations") != "DISABLED"
            or market_status.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or market_status.get("matched_count") != market_pairs.get("matched_count")
            or market_pairs.get("status") != market_status.get("status")):
        raise ValueError("INVALID_FREE_MARKET_RESEARCH_LAYER")
    if (coverage.get("production_recommendations") != "DISABLED"
            or coverage.get("results_independently_verified_all_leagues") is not False
            or len(coverage.get("league_coverage", [])) != 6):
        raise ValueError("INVALID_SIX_LEAGUE_AUDIT")
    if (ab.get("production_recommendations") != "DISABLED"
            or ab.get("promotion_allowed") is not False
            or ab.get("status") not in ("SHADOW_ONLY", "HOLD")
            or ab.get("candidate_count") != shadow.get("predictions_count")):
        raise ValueError("INVALID_SHADOW_AB_STATE")
    if (center.get("production_recommendations") != "DISABLED"
            or center.get("six_league_result_verification_complete") is not False
            or center.get("total_completed_comparable_samples") != validation.get("forward_archive_samples", 0)
            or center.get("total_strict_market_pairs") != market_status.get("matched_count")):
        raise ValueError("INCONSISTENT_RESEARCH_CENTER_DATA")
    if (gate.get("status") != "HOLD"
            or gate.get("production_recommendations") != "DISABLED"
            or gate.get("automated_release_supported") is not False
            or gate.get("model_promoted") is not False
            or gate.get("settled_samples") != center.get("total_completed_comparable_samples")):
        raise ValueError("INVALID_PRODUCTION_QUALIFICATION_GATE")
    if (selections.get("schema") != "football-king-explainable-research-selections-v1"
            or selections.get("production_recommendations") != "DISABLED"
            or selections.get("selection_mode") != "SHADOW_RESEARCH_ONLY"
            or selections.get("automatic_bets") is not False
            or selections.get("validated_positive_expected_value") is not False
            or selections.get("model_is_uncalibrated") is not True
            or selections.get("market_prices_are_not_executable") is not True
            or selections.get("estimated_roi") is not None
            or selections.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or not isinstance(selections.get("selections"), list)
            or not isinstance(selections.get("reviews"), list)
            or selections.get("selected_count") != len(selections["selections"])
            or selections.get("paired_count") != market_status.get("matched_count")
            or selections.get("selected_count", 0) > selections.get("paired_count", 0)):
        raise ValueError("INVALID_RESEARCH_RECOMMENDATIONS")
    for item in selections["selections"] + selections["reviews"]:
        if (not isinstance(item, dict)
                or item.get("production_recommendations") != "DISABLED"
                or item.get("executable_market_odds_available") is not False
                or item.get("value_bet_verified") is not False
                or item.get("suggested_stake") is not None
                or item.get("reliability") != "UNCALIBRATED_RESEARCH_ONLY"):
            raise ValueError("UNSAFE_RESEARCH_SELECTION_CONTENT")
    if source.count('id="fk-recommendations"') != 1 or 'id="fk-picks"' not in source:
        raise ValueError("MISSING_VISIBLE_RESEARCH_RECOMMENDATIONS")
    if (source.count('id="fk-hub"') != 1
            or 'src="research_hub.js"' not in source
            or 'href="research_hub.css"' not in source
            or not (site / "research_hub.js").is_file()
            or not (site / "research_hub.css").is_file()):
        raise ValueError("MISSING_MOBILE_RESEARCH_DASHBOARD")
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
        '。概率未校準；即使已有賠率，仍須經樣本外驗證，嚴禁視作投注建議。</p>' +
        ('<div class="scroll"><table><thead><tr><th>聯賽</th><th>球隊</th>'
         '<th>主勝 / 和局 / 客勝（研究概率）</th></tr></thead><tbody>' +
         forecast_rows + '</tbody></table></div>' if forecast_rows else
         '<p class="small">今次沒有符合訓練量及準確開賽時間條件嘅賽前候選。</p>') +
        '<p><a href="shadow.json">查看影子研究紀錄（JSON）</a></p></section>')
    if 'id="shadow-research-only"' not in source:
        source = source.replace("</body>", shadow_panel + "</body>", 1)
    crosscheck_panel = _section(
        "independent-source-check", "獨立來源交叉核對（只涵蓋部分德甲）",
        ("德甲雙來源配對：" + str(crosscheck.get("matched_identical_home_away", 0)) +
         "；可比較賽果：" + str(crosscheck.get("score_comparisons", 0)) +
         "；衝突：" + str(crosscheck.get("score_conflicts", 0)) +
         "。沒有配對不能推斷一致；其他五個聯賽及準確開賽時間尚未獨立核實。"),
        "crosscheck.json")
    if 'id="independent-source-check"' not in source:
        source = source.replace("</body>", crosscheck_panel + "</body>", 1)
    market_panel = _section(
        "free-market-research", "免費賠率基準及時間點配對",
        ("賠率資料狀態：" + str(market_status.get("source_state", "HOLD")) +
         "；市場賽事：" + str(market_status.get("market_events", 0)) +
         "；合資格賽前嚴格配對：" + str(market_status.get("matched_count", 0)) +
         "；模型時間配對狀態：" + str(market_status.get("reason", "UNKNOWN")) +
         "。比較只供研究，唔係價值投注或盈利證據。"),
        "market_status.json")
    if 'id="free-market-research"' not in source:
        source = source.replace("</body>", market_panel + "</body>", 1)
    hub_panel = _section(
        "research-qualification",
        "六大聯賽樣本外驗證及正式推薦資格",
        ("六聯賽雙來源開賽時間一致：" +
         str(coverage.get("total_confirmed_kickoffs", 0)) +
         "；未校準A/B候選：" + str(ab.get("candidate_count", 0)) +
         "；已結算樣本：" + str(gate.get("settled_samples", 0)) +
         "；九項正式審核：HOLD；" +
         str(len(gate.get("failed_conditions", []))) + "項仍待通過。"
         "即使通過亦需要獨立審核，絕不自動推薦下注。"),
        "production_gate.json")
    if 'id="research-qualification"' not in source:
        source = source.replace("</body>", hub_panel + "</body>", 1)
    for key, title, description, link in required_sections:
        if 'id="' + key + '"' not in source:
            source = source.replace("</body>", _section(key, title, description, link) + "</body>", 1)
    for key, _, _, _ in required_sections:
        if source.count('id="' + key + '"') != 1:
            raise ValueError("DUPLICATE_OR_MISSING_SAFETY_SECTION_" + key)
    if source.count('id="shadow-research-only"') != 1:
        raise ValueError("MISSING_SHADOW_RESEARCH_WARNING")
    if source.count('id="independent-source-check"') != 1:
        raise ValueError("MISSING_INDEPENDENT_SOURCE_WARNING")
    if source.count('id="free-market-research"') != 1:
        raise ValueError("MISSING_MARKET_RESEARCH_WARNING")
    if source.count('id="research-qualification"') != 1:
        raise ValueError("MISSING_RESEARCH_QUALIFICATION_SECTION")
    if 'src="freshness.js"' not in source:
        raise ValueError("MISSING_CLIENT_FRESHNESS_SCRIPT")
    if 'id="no-js-freshness-warning"' not in source:
        source = source.replace("</body>", (
            '<noscript><p id="no-js-freshness-warning">警告：瀏覽器停用 JavaScript，'
            '無法自動檢查報告有冇過期。請以報告時間戳為準；'
            '未驗證嘅影子概率不可當作投注建議。</p></noscript></body>'), 1)
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
