"""Public, zero-secret, fail-closed production-readiness dashboard.

This is an explanatory view of already-published aggregate evidence. Never
imports bookmaker raw odds or marks unverified betting picks as certified.
"""
import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path

from ops.recommendation_readiness import grounded_progress, _read_json
from ops.private_summary_archive import check as validate_private_aggregate

EXPECTED_GATE_KEYS = (
    "utc_fixture_identity", "source_time_quota_licence", "paired_asian_totals",
    "bookmaker_cross_feed_dedupe", "sealed_point_in_time",
    "out_of_sample_calibration", "model_promotion_safety",
)


def _fresh(value, now, hours):
    try:
        if not isinstance(value, str):
            return False
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return False
        age = (now - parsed.astimezone(timezone.utc)).total_seconds()
        return -300 <= age <= hours * 3600
    except (ValueError, TypeError, OverflowError):
        return False


def build(settled, quality, market, now=None, private_summary=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("NAIVE_NOW")
    if not all(isinstance(x, dict) for x in (settled, quality, market)):
        raise ValueError("INVALID_SOURCE")
    p = grounded_progress(settled, quality, {}, market)
    raw_checks = quality.get("checks")
    checks = {}
    if isinstance(raw_checks, list):
        for item in raw_checks:
            if (isinstance(item, dict)
                    and item.get("key") in EXPECTED_GATE_KEYS
                    and item.get("key") not in checks):
                checks[item["key"]] = item.get("state")
    passed = sum(checks.get(k) == "PASS" for k in EXPECTED_GATE_KEYS)
    archived = p["settled_cases_in_archive"]
    verified_flagged = p["independently_verified_result_cases"]
    quality_fresh = _fresh(quality.get("captured_utc"), now, 36)
    market_fresh = _fresh(market.get("as_of_utc"), now, 26)
    private_status = "NOT_RECORDED"
    private_h2h_count = 0
    private_updated = None
    if isinstance(private_summary, dict) and private_summary:
        try:
            validate_private_aggregate(private_summary, now)
            private_updated = private_summary["captured_utc"]
            if _fresh(private_updated, now, 26):
                private_status = private_summary["input_status"]
                if private_status == "CONNECTED" and private_summary["requested_markets"] == ["h2h"]:
                    private_h2h_count = private_summary["counts"]["RESEARCH_ONLY"]
            else:
                private_status = "STALE"
        except (ValueError, TypeError):
            private_status = "INVALID_OR_STALE"
    return {
        "schema": "football-king-public-recommendation-progress-v1",
        "generated_utc": now.isoformat(),
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "official_recommendation_count": 0,
        "recorded_settled_cases": archived,
        "result_rows_marked_independently_verified": verified_flagged,
        "independent_verification_not_cryptographically_authenticated": True,
        "required_independently_verified_cases": 300,
        "still_needed_if_existing_rows_pass_independent_audit": max(0, 300 - verified_flagged),
        "recorded_week_blocks": p["independent_week_blocks"],
        "minimum_week_blocks": 12,
        "leagues_with_at_least_40_recorded_cases": p["leagues_with_40_settlements"],
        "minimum_leagues_with_40": 4,
        "quality_gates_passed": passed,
        "quality_gates_total": len(EXPECTED_GATE_KEYS),
        "quality_fresh": quality_fresh,
        "market_baseline_fresh": market_fresh,
        "market_baseline_event_count": (
            market.get("event_count", 0)
            if market_fresh and market.get("status") == "RESEARCH_ONLY"
            and type(market.get("event_count")) is int else 0),
        "private_quote_collector_status": private_status,
        "private_h2h_research_quote_count": private_h2h_count,
        "private_quote_captured_utc": private_updated,
        "actual_bettable_odds_verified": False,
        "independent_model_calibration_verified": False,
        "risk_adjusted_ev_verified": False,
        "trusted_final_manual_approval_verified": False,
        "blockers": [
            "INSUFFICIENT_AUTHENTICATED_FORWARD_SETTLEMENT",
            "UNVERIFIED_INDEPENDENT_MODEL_CALIBRATION",
            "NO_CERTIFIED_EXECUTABLE_QUOTES",
            "NO_PRODUCTION_APPROVAL",
        ],
        "notice": "研究選向不等於正式投注建議；來源時間、模型及賽果仍須獨立驗收。",
    }


def render_section(progress):
    esc = html.escape
    stage = "正式推薦：暫停（HOLD）"
    count = int(progress["recorded_settled_cases"])
    certified = int(progress["result_rows_marked_independently_verified"])
    gates = int(progress["quality_gates_passed"])
    warns = []
    if not progress["quality_fresh"]:
        warns.append("七項品質資料已過期或時間不可核實")
    if not progress["market_baseline_fresh"]:
        warns.append("市場比較快照已過期或不可核實")
    freshness = "；".join(warns) if warns else "品質及市場快照仍在允許時效內"
    if progress["private_quote_collector_status"] == "CONNECTED":
        private_info = (f"已採集私人 API 賽前獨贏研究報價："
                        f"{progress['private_h2h_research_quote_count']} 筆；"
                        "不包含已認證可下注盤口。")
    else:
        private_info = ("私人賠率資料暫不可用或未更新（"
                        + str(progress["private_quote_collector_status"]) + "）。")
    summary = (f"正式推薦資格：7項品質檢查通過 {gates}/7；"
               f"已封存結算 {count} 場，來源標示獨立核實 {certified}/300 場；"
               f"已記錄 {progress['recorded_week_blocks']}/12 個週次。")
    return (
        '<section id="fk-official-readiness" role="status" aria-live="polite">'
        '<h2>足球王者｜正式推薦驗收進度</h2>'
        '<p><strong>' + esc(stage) + '</strong></p>'
        '<p>' + esc(summary) + '</p>'
        '<p class="small">' + esc(freshness) + '</p>'
        '<p class="small">' + esc(private_info) + '</p>'
        '<p class="small">獨立核實標記未等於第三方認證。'
        '尚缺獨立概率校準、合法可執行賠率、完整前瞻評估及正式審批。</p>'
        '<p class="small"><a href="official_readiness.json">'
        '查看完整驗收數據</a>｜研究方向請看下方研究首選。</p>'
        '</section>'
    )


def publish(site, settled, gates, market, now=None, private_summary=None):
    site = Path(site)
    path = site / "index.html"
    markup = path.read_text(encoding="utf-8")
    if 'id="fk-official-readiness"' in markup:
        raise ValueError("READINESS_SECTION_ALREADY_PRESENT")
    report = build(_read_json(settled), _read_json(gates), _read_json(market), now,
                   _read_json(private_summary) if private_summary is not None else None)
    section = render_section(report)
    anchor = '<h2>近期賽程與賽果</h2>'
    if anchor in markup:
        markup = markup.replace(anchor, section + anchor, 1)
    elif "</main>" in markup:
        markup = markup.replace("</main>", section + "</main>", 1)
    else:
        raise ValueError("NO_SAFE_INSERTION_POINT")
    (site / "official_readiness.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.write_text(markup, encoding="utf-8")
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--settled", default="evidence/settled.json")
    p.add_argument("--gates", default="sources/seven_quality_gates_latest.json")
    p.add_argument("--market", default="market/latest.json")
    p.add_argument("--private-summary", default="market/private_summary_latest.json")
    args = p.parse_args()
    report = publish(args.site, args.settled, args.gates, args.market,
                     private_summary=args.private_summary)
    print("OFFICIAL_READINESS:", report["status"],
          "SEALED:", report["recorded_settled_cases"],
          "VERIFIED_FLAGGED:", report["result_rows_marked_independently_verified"],
          "QUALITY:", report["quality_gates_passed"], "/7")


if __name__ == "__main__":
    main()
