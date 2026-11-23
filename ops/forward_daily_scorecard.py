"""Daily transparent forward 1X2 scoreboard from already sealed, settled observations.

Descriptive only: public-source final scores have not been independently authenticated.
Never synthesize missing market quotes or post-hoc challenger forecasts.
"""
import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo
from pathlib import Path
from evidence_merge import validate
from market_shrinkage import blend

WEIGHTS = (0.0, 0.5, 0.75, 1.0)
TARGET = 1000
OUTCOMES = ("home", "draw", "away")


def _review_counts():
    return {field: 0 for field in (
        "observations", "model_correct", "model_incorrect", "market_correct", "market_incorrect",
        "both_correct", "both_wrong", "model_wrong_market_right", "model_right_market_wrong")}


def _error_review(rows, daily):
    """Describe observed mistakes; never refit or reconstruct a sealed challenger."""
    counts = _review_counts()
    daily_counts = {day: _review_counts() for day in daily}
    matrices = {name: [[0] * 3 for _ in range(3)]
                for name in ("original_model", "market_baseline")}
    directions = {f"predicted_{predicted}_actual_{actual}": 0
                  for predicted in OUTCOMES for actual in OUTCOMES if predicted != actual}
    worst = []
    for day, cases in daily.items():
        for row in cases:
            p, m = blend(row["p"], row["m"], 0.0), blend(row["p"], row["m"], 1.0)
            y = row["y"]
            predicted, market = (max(range(3), key=lambda i: vector[i]) for vector in (p, m))
            model_hit, market_hit = predicted == y, market == y
            matrices["original_model"][y][predicted] += 1
            matrices["market_baseline"][y][market] += 1
            category = ("both_correct" if model_hit and market_hit else
                        "both_wrong" if not model_hit and not market_hit else
                        "model_right_market_wrong" if model_hit else "model_wrong_market_right")
            for group in (counts, daily_counts[day]):
                group["observations"] += 1
                group["model_correct" if model_hit else "model_incorrect"] += 1
                group["market_correct" if market_hit else "market_incorrect"] += 1
                group[category] += 1
            if not model_hit:
                directions[f"predicted_{OUTCOMES[predicted]}_actual_{OUTCOMES[y]}"] += 1
                model_loss, market_loss = (-math.log(max(vector[y], 1e-15)) for vector in (p, m))
                case = {field: row[field] for field in
                        ("key", "league", "forecast_utc", "market_utc", "kickoff_utc", "y")}
                case.update(p=list(row["p"]), m=list(row["m"]), model_top_choice=predicted,
                            market_top_choice=market, model_correct=False, market_correct=market_hit,
                            model_log_loss=round(model_loss, 6), market_log_loss=round(market_loss, 6),
                            model_minus_market_log_loss=round(model_loss-market_loss, 6))
                # Rank on unrounded loss; keys make equal-loss ordering deterministic.
                worst.append((model_loss, case))
    worst.sort(key=lambda item: (-item[0], item[1]["kickoff_utc"], item[1]["key"]))
    return {
        "schema": "football-king-forward-error-review-v1",
        "status": "RESEARCH_ONLY" if rows else "HOLD",
        "sample_count": len(rows), "same_cases_for_model_and_market": True,
        "model_probability_basis": "SEALED_ORIGINAL_P_AND_SAME_CUTOFF_MARKET_M_NORMALIZED",
        "outcome_order": list(OUTCOMES),
        "confusion_matrix_axes": {"rows": "actual", "columns": "predicted"},
        "confusion_matrices": matrices if rows else None,
        "summary": counts if rows else None,
        "daily_hk": [{"date": day, **daily_counts[day]} for day in sorted(daily_counts)],
        "direction_counts": directions,
        "worst_model_misses": [case for _, case in worst[:10]],
        "worst_case_limit": 10,
        "review_priority_basis": "OBSERVED_MISCLASSIFICATION_AND_ORIGINAL_MODEL_LOG_LOSS_ONLY",
        "statistical_causation_proven": False,
        "automatic_parameter_changes": False, "automatic_model_promotion": False,
        "results_independently_verified": False, "production_recommendations": "DISABLED",
    }


def _scores(rows, weight):
    if not rows:
        return None
    hits = 0
    ll = brier = rps = 0.0
    for row in rows:
        p = blend(row["p"], row["m"], weight)
        y = row["y"]
        hits += int(max(range(3), key=lambda i: p[i]) == y)
        ll -= math.log(max(p[y], 1e-15))
        brier += sum((v - int(i == y)) ** 2 for i, v in enumerate(p))
        rps += ((p[0] - int(y == 0)) ** 2 +
                (p[0] + p[1] - int(y <= 1)) ** 2) / 2
    n = len(rows)
    return {"n": n, "correct": hits, "accuracy": round(hits/n, 6),
            "log_loss": round(ll/n, 6), "brier": round(brier/n, 6),
            "rps": round(rps/n, 6)}


def build(evidence):
    rows = validate(evidence)
    checked = datetime.fromisoformat(evidence["checked_utc"].replace("Z", "+00:00"))
    daily = defaultdict(list)
    daily_utc = defaultdict(list)
    for row in rows:
        stamp = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("NAIVE_KICKOFF")
        if stamp + timedelta(minutes=120) > checked:
            raise ValueError("SETTLEMENT_NOT_MATURE_AT_CHECKED_UTC")
        if not isinstance(row.get("league"), str) or not row["league"].strip():
            raise ValueError("INVALID_SETTLED_LEAGUE")
        day = stamp.astimezone(ZoneInfo('Asia/Hong_Kong')).date().isoformat()
        daily[day].append(row)
        daily_utc[stamp.astimezone(timezone.utc).date().isoformat()].append(row)
    def compare(items):
        return {f"{weight:.2f}": _scores(items, weight) for weight in WEIGHTS}
    return {
        "schema": "football-king-forward-daily-scorecard-v1",
        "status": "RESEARCH_ONLY" if rows else "HOLD",
        "as_of_utc": evidence["checked_utc"],
        "settled_observations": len(rows),
        "target_observations": TARGET,
        "remaining_to_target": max(0, TARGET - len(rows)),
        "independently_verified_observations": 0,
        "observed_match_dates": len(daily),
        "weights": {"0.00": "original_model", "0.50": "half_market",
                    "0.75": "three_quarters_market", "1.00": "market_baseline"},
        "cumulative": compare(rows),
        "daily_hk": [
            {"date": day, "observations": len(daily[day]),
             "comparisons": compare(daily[day])}
            for day in sorted(daily)
        ],
        "daily_utc": [
            {"date": day, "observations": len(daily_utc[day]),
             "comparisons": compare(daily_utc[day])}
            for day in sorted(daily_utc)
        ],
        "error_review": _error_review(rows, daily),
        "same_cases_for_all_four_weights": True,
        "retrospective_reconstruction_of_blends": True,
        "independent_forward_challenger_registration_proven": False,
        "market_quotes_are_executable": False,
        "results_independently_verified": False,
        "statistical_superiority_proven": False,
        "production_recommendations": "DISABLED",
        "warning": "Observational scores on recorded point-in-time model/market pairs; outcomes are not independently verified. Blend comparisons are retrospective, not separately sealed forward challengers. Accuracy does not establish betting profitability.",
    }


def _review_page(report):
    review = report["error_review"]
    rows = []
    for day in reversed(review["daily_hk"]):
        cells = [day["date"], day["observations"], day["model_correct"], day["market_correct"],
                 day["model_wrong_market_right"], day["model_right_market_wrong"]]
        rows.append("<tr>" + "".join("<td>" + escape(str(value)) + "</td>" for value in cells) + "</tr>")
    count = review["sample_count"]
    if count:
        summary = review["summary"]
        overview = (f"<p>已記錄完賽研究個案：{count}；原模型命中：{summary['model_correct']}；"
                    f"同期市場首選命中：{summary['market_correct']}。</p>")
        table = ('<div class="table"><table><thead><tr><th>香港比賽日</th><th>場數</th>'
                 '<th>模型命中</th><th>市場命中</th><th>模型未中／市場中</th>'
                 '<th>模型中／市場未中</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>')
    else:
        overview, table = '<p>資料不足：暫無符合完賽時間條件的已封存研究個案。</p>', ''
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>每日模擬覆盤</title><style>body{font-family:system-ui,sans-serif;max-width:960px;'
            'margin:24px auto;padding:0 16px;line-height:1.6}.table{overflow-x:auto}'
            'table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid #ccc;'
            'text-align:left;white-space:nowrap}.notice{padding:12px;background:#fff3cd}</style></head><body>'
            '<h1>每日模擬覆盤</h1><p class="notice">研究觀察；賽果來源未經獨立核實。非投注建議。'
            '統計供錯例回顧；模型改善須以之後的比賽檢驗。</p>'
            '<p>資料核對時刻（UTC）：' + escape(report["as_of_utc"]) + '</p>' + overview + table +
            '<p>兩類差異只協助檢查錯例，不能證明原因或作自動調參依據。'
            '原模型與市場使用同一批已封存個案；既有混合權重比較屬事後研究重建。</p>'
            '<p><a href="forward_daily_scorecard.json" download>下載完整研究覆盤 JSON（含逐場追溯）</a>'
            ' · <a href="index.html">返回研究首頁</a></p></body></html>')


def _link_review(index):
    # The generated block is static; fixture keys and team names never enter HTML.
    if re.search(r'''\bhref\s*=\s*(["'])daily-review\.html\1''', index, re.IGNORECASE):
        return index
    link = '<p id="daily-review-nav"><a href="daily-review.html">每日模擬覆盤</a></p>\n'
    closing = index.lower().rfind('</body>')
    return index[:closing] + link + index[closing:] if closing >= 0 else index + '\n' + link


def publish(source, site):
    p = Path(source)
    if p.is_file():
        evidence = json.loads(p.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"SETTLED_EVIDENCE_MISSING: {p}")
    result = build(evidence)
    dest = Path(site)
    page = _review_page(result)
    index = dest / "index.html"
    linked = _link_review(index.read_text(encoding="utf-8")) if index.is_file() else None
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "forward_daily_scorecard.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (dest / "daily-review.html").write_text(page, encoding="utf-8")
    if linked is not None:
        index.write_text(linked, encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="evidence/settled.json")
    parser.add_argument("--site", default="app/site")
    args = parser.parse_args()
    report = publish(args.input, args.site)
    print(json.dumps({"status": report["status"],
                      "settled_observations": report["settled_observations"],
                      "remaining_to_target": report["remaining_to_target"]}))
