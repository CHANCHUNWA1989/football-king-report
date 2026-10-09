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
    extra = _json(site / "extra_sources.json")
    extensions = _json(site / "free_research_extensions.json")
    wide = _json(site / "wide_leagues.json")
    weather = _json(site / "weather_context.json")
    bsd = _json(site / "bsd_backup.json")
    integrity = _json(site / "fixture_integrity.json")
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
    if (selections.get("fallback_mode") not in ("NOT_NEEDED", "MODEL_ONLY_LOW_EVIDENCE")
            or selections.get("model_only_is_betting_advice") is not False
            or not isinstance(selections.get("model_only_watchlist"), list)
            or selections.get("model_only_count") != len(selections["model_only_watchlist"])
            or selections["model_only_count"] > 5):
        raise ValueError("UNSAFE_MODEL_ONLY_FALLBACK")
    existing_pairs = {
        (p.get("league"), p.get("home"), p.get("away"), p.get("kickoff_utc"))
        for p in market_pairs.get("comparisons", []) if isinstance(p, dict)
    }
    seen_model_only = set()
    from team_identity import team_id
    for item in selections["model_only_watchlist"]:
        if (not isinstance(item, dict)
                or item.get("production_recommendations") != "DISABLED"
                or item.get("reliability") != "LOW_UNVALIDATED_NO_MARKET"
                or item.get("market_confirmed") is not False
                or item.get("qualifies_for_betting") is not False
                or item.get("executable_market_odds_available") is not False
                or item.get("value_bet_verified") is not False
                or item.get("suggested_stake") is not None):
            raise ValueError("UNSAFE_MODEL_ONLY_FALLBACK_ITEM")
        key = (item.get("league"), team_id(item.get("league"), item.get("home")),
               team_id(item.get("league"), item.get("away")), item.get("kickoff_utc"))
        if key in seen_model_only or not all(key):
            raise ValueError("MODEL_ONLY_FALLBACK_DUPLICATE")
        seen_model_only.add(key)
        for row in existing_pairs:
            if (key[0] == row[0] and key[1] == team_id(row[0], row[1])
                    and key[2] == team_id(row[0], row[2]) and key[3] == row[3]):
                raise ValueError("MODEL_ONLY_REUSED_MARKET_PAIRED_EVENT")
    if selections["model_only_count"] and (
            selections.get("fallback_mode") != "MODEL_ONLY_LOW_EVIDENCE"
            or selections.get("status") != "RESEARCH_ONLY"):
        raise ValueError("MODEL_ONLY_FALLBACK_UNSAFE_STATUS")
    if (source.count('id="fk-model-only-section"') != 1
            or source.count('id="fk-model-only-list"') != 1):
        raise ValueError("MISSING_VISIBLE_FALLBACK_DISCLOSURE")
    if source.count('id="fk-recommendations"') != 1 or 'id="fk-picks"' not in source:
        raise ValueError("MISSING_VISIBLE_RESEARCH_RECOMMENDATIONS")
    if (bsd.get("schema")!="football-king-bsd-optional-market-overlay-v1"
            or bsd.get("production_recommendations")!="DISABLED"
            or bsd.get("status") not in ("HOLD","RESEARCH_ONLY")
            or bsd.get("automatic_replacement_of_main_market") is not False
            or bsd.get("market_is_executable") is not False
            or bsd.get("real_money_recommendations") is not False
            or bsd.get("compared_to_primary_model") not in (False,True)
            or bsd.get("source_licence_verified_for_derived_research") is not True
            or type(bsd.get("time_valid_shadow_pairs")) is not int
            or bsd["time_valid_shadow_pairs"] < 0
            or bsd["time_valid_shadow_pairs"] > bsd.get("market_event_count",0)
            or source.count('id="fk-bsd-backup"') != 1):
        raise ValueError("INVALID_BSD_FREE_MARKET_BACKUP")
    if (weather.get("schema") != "football-king-research-weather-overlay-v1"
            or weather.get("production_recommendations") != "DISABLED"
            or weather.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or weather.get("source_is_city_centre_not_venue") is not True
            or weather.get("match_venue_confirmed") is not False
            or weather.get("included_as_predictive_model_feature") is not False
            or weather.get("weather_impact_on_win_probability_validated") is not False
            or weather.get("market_odds_source") is not False
            or weather.get("data_license") != "https://creativecommons.org/licenses/by/4.0/"
            or not isinstance(weather.get("forecasts"),list)
            or len(weather.get("forecasts",[])) > 12
            or source.count('id="fk-met-weather"') != 1):
        raise ValueError("INVALID_MET_WEATHER_RESEARCH_PROVENANCE")
    for row in weather["forecasts"]:
        if (not isinstance(row,dict)
                or row.get("league") != "bundesliga"
                or row.get("production_recommendations") != "DISABLED"
                or row.get("used_in_model") is not False
                or row.get("geography") != "CITY_CENTRE_PROXY_NOT_VERIFIED_STADIUM"):
            raise ValueError("INVALID_MET_WEATHER_FORECAST_ITEM")
    if (extra.get("schema") != "football-king-source-overlay-v1"
            or extra.get("production_recommendations") != "DISABLED"
            or extra.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or extra.get("source_samples_used_as_forecast_training") is not False
            or extra.get("independently_verified_six_league_results") is not False
            or extra.get("can_replace_market_1x2") is not False
            or not isinstance(extra.get("providers"), list)
            or len(extra.get("providers", [])) != 4
            or any(p.get("provider") not in
                   ("thesportsdb", "api_football", "football_data_org", "sportmonks")
                   for p in extra["providers"] if isinstance(p, dict))
            or source.count('id="fk-extra-sources"') != 1):
        raise ValueError("INVALID_ADDITIONAL_FREE_SOURCE_PROVENANCE")
    if (extensions.get("schema") != "football-king-free-research-extension-site-v1"
            or extensions.get("production_recommendations") != "DISABLED"
            or extensions.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or extensions.get("historical_data_only_cannot_validate_current_season") is not True
            or extensions.get("no_paid_or_unlicensed_1x2_quotes") is not True
            or extensions.get("used_to_promote_model") is not False
            or not isinstance(extensions.get("providers"), list)
            or [p.get("provider") for p in extensions["providers"] if isinstance(p,dict)] !=
                  ["openfootapi","statsbomb_open_data"]
            or source.count('id="fk-research-extensions"') != 1):
        raise ValueError("INVALID_FREE_RESEARCH_EXTENSION_PROVENANCE")
    if (wide.get("schema") != "football-king-global-free-league-site-v1"
            or wide.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or wide.get("production_recommendations") != "DISABLED"
            or wide.get("backup_policy") != "PRECISE_OPENLIGA_UTC_SCHEDULE_ONLY"
            or not isinstance(wide.get("backup_scheduled_fixtures"), list)
            or len(wide["backup_scheduled_fixtures"]) > 9
            or wide.get("provider_market_odds_available") is not False
            or wide.get("training_evidence_validated") is not False
            or wide.get("historic_data_can_be_presented_as_live") is not False
            or wide.get("source_count") != 2
            or wide.get("provider_names") != ["openfootball_json", "openligadb"]
            or wide.get("league_file_total") != 30
            or not isinstance(wide.get("league_cards"), list)
            or len(wide["league_cards"]) != 30
            or not all(isinstance(item, dict) and
                       item.get("provider") in ("openfootball_json", "openligadb")
                       and item.get("access_status") in (
                           "FETCHED", "NO_FILE_OR_ACCESS", "RATE_LIMITED",
                           "NETWORK_ERROR", "INVALID_SCHEMA_OR_RESPONSE",
                           "TIME_BUDGET_EXHAUSTED", "HTTP_ERROR",
                           "NOT_YET_COLLECTED")
                       for item in wide["league_cards"])
            or source.count('id="fk-wide-sources"') != 1):
        raise ValueError("UNSAFE_OR_MISSING_GLOBAL_FREE_LEAGUES")
    for row in wide["backup_scheduled_fixtures"]:
        if (not isinstance(row,dict)
                or row.get("source") != "openligadb"
                or row.get("backup_for_schedule_only") is not True
                or row.get("market_confirmed") is not False
                or row.get("betting_recommendation") is not False
                or row.get("production_recommendations") != "DISABLED"):
            raise ValueError("UNSAFE_GLOBAL_BACKUP_FIXTURES")
    if (integrity.get("schema") != "football-king-fixture-integrity-v1"
            or integrity.get("production_recommendations") != "DISABLED"
            or integrity.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or integrity.get("blocked_from_research_recommendations") is not True
            or integrity.get("never_used_to_rewrite_frozen_forecasts") is not True
            or integrity.get("no_independent_result_verification_claim") is not True
            or not isinstance(integrity.get("disagreements"), list)
            or integrity.get("conflicting_kickoff_observations") != len(integrity["disagreements"])
            or len(integrity["disagreements"]) > 100
            or source.count('id="fk-fixture-integrity"') != 1):
        raise ValueError("INVALID_FREE_FIXTURE_CONSENSUS")
    from team_identity import team_id
    conflict_keys = set()
    for conflict in integrity["disagreements"]:
        if (not isinstance(conflict, dict)
                or conflict.get("action") != "SUSPEND_RESEARCH_SELECTION_PENDING_SCHEDULE_REVIEW"
                or conflict.get("production_recommendations") != "DISABLED"):
            raise ValueError("UNSAFE_FIXTURE_CONFLICT_ITEM")
        lg=conflict.get("league")
        try:
            key=(lg,team_id(lg,conflict.get("home")),
                 team_id(lg,conflict.get("away")), _utc(conflict["original_kickoff_utc"]).isoformat())
        except (ValueError, KeyError, TypeError, OverflowError):
            raise ValueError("INVALID_FIXTURE_CONFLICT_TIME") from None
        conflict_keys.add(key)
    for suggestion in (selections.get("selections", [])
                       + selections.get("reviews", [])
                       + selections.get("model_only_watchlist", [])):
        lg=suggestion.get("league")
        try:
            key=(lg,team_id(lg,suggestion.get("home")),
                 team_id(lg,suggestion.get("away")), _utc(suggestion["kickoff_utc"]).isoformat())
        except (TypeError, KeyError, ValueError, OverflowError):
            raise ValueError("INVALID_SELECTION_SCHEDULE") from None
        if key in conflict_keys:
            raise ValueError("CONFLICTING_FIXTURE_CANNOT_BE_RECOMMENDED")
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
