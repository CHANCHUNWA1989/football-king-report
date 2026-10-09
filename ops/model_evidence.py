"""Conservative 1X2 shadow backtest vs time-matched market baseline.

Without immutable, timestamped genuine forecasts, this is analysis only,
never permission to issue picks. Do not infer ROI from probability scores.
"""
import argparse
import csv
import html
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


OUTCOMES = ("home", "draw", "away")
HEADER = {"case_id", "prediction_utc", "market_utc", "kickoff_utc",
          "p_home", "p_draw", "p_away", "m_home", "m_draw", "m_away", "outcome"}


def when(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def probs(row, prefix):
    vals = [float(row[prefix + "_" + x]) for x in OUTCOMES]
    if any(not math.isfinite(v) or not 0 <= v <= 1 for v in vals):
        raise ValueError("INVALID_PROBABILITY")
    if abs(sum(vals) - 1) > 0.0001:
        raise ValueError("PROBABILITY_SUM_NOT_ONE")
    return vals


def read_rows(path):
    path = Path(path)
    if path.stat().st_size > 10_000_000:
        raise ValueError("SHADOW_CSV_TOO_LARGE")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not HEADER.issubset(set(reader.fieldnames or [])):
            raise ValueError("REQUIRED_COLUMNS_MISSING")
        rows = list(reader)
    if len(rows) > 30000:
        raise ValueError("TOO_MANY_SHADOW_ROWS")
    events, valid = set(), []
    for r in rows:
        key = r.get("case_id", "")
        if not key or key in events:
            raise ValueError("MISSING_OR_DUPLICATE_CASE_ID")
        events.add(key)
        pred, market, kickoff = when(r["prediction_utc"]), when(r["market_utc"]), when(r["kickoff_utc"])
        # Same-or-earlier baseline snapshot, at least 10 minutes before kickoff.
        if not (market <= pred <= kickoff - __import__("datetime").timedelta(minutes=10)):
            raise ValueError("LEAKAGE_OR_MISMATCHED_MARKET_TIME")
        if (pred - market).total_seconds() > 72 * 3600:
            raise ValueError("BASELINE_TOO_OLD")
        p, m = probs(r, "p"), probs(r, "m")
        outcome = r.get("outcome", "")
        if outcome not in OUTCOMES:
            if not outcome:  # Unsettled fixture; never infer its outcome.
                continue
            raise ValueError("INVALID_MATCH_OUTCOME")
        y = OUTCOMES.index(outcome)
        valid.append({"date": kickoff.date().isoformat(), "kickoff": kickoff,
                      "pred": pred, "market": market, "p": p, "m": m, "y": y})
    valid.sort(key=lambda item: item["kickoff"])
    return valid


def losses(row, key):
    v = row[key]
    y = row["y"]
    return (-math.log(max(v[y], 1e-15)),
            sum((v[j] - float(j == y)) ** 2 for j in range(3)))


def evaluate(rows, *, immutable_evidence=False, bootstrap_runs=400):
    n = len(rows)
    result = {
        "status": "HOLD", "n": n, "market_baseline_comparable": bool(n),
        "time_validated": True, "immutable_forecast_evidence_verified": bool(immutable_evidence),
        "production_recommendations": "DISABLED", "certified_profitable_model": False,
        "reason": "NO_SETTLED_COMPARABLE_FORECASTS" if not n else "INSUFFICIENT_INDEPENDENT_SAMPLE",
        "measurements": None,
    }
    if not n:
        return result
    week_groups = defaultdict(list)
    model_ll = market_ll = model_brier = market_brier = 0.0
    for row in rows:
        a, b = losses(row, "p")
        c, d = losses(row, "m")
        model_ll += a
        model_brier += b
        market_ll += c
        market_brier += d
        week = row["kickoff"].strftime("%G-W%V")
        week_groups[week].append(c - a)
    result["measurements"] = {
        "model_log_loss": round(model_ll / n, 6),
        "market_log_loss": round(market_ll / n, 6),
        "model_brier": round(model_brier / n, 6),
        "market_brier": round(market_brier / n, 6),
        "market_minus_model_log_loss": round((market_ll - model_ll) / n, 6),
    }
    if n < 300 or len(week_groups) < 12:
        return result
    # Week-block bootstrap (not iid-match bootstrap) to reduce within-round dependence.
    weeks = list(week_groups.values())
    rng = random.Random(20261009)
    estimates = []
    for _ in range(bootstrap_runs):
        sampled = [weeks[rng.randrange(len(weeks))] for _ in weeks]
        values = [v for group in sampled for v in group]
        estimates.append(sum(values) / len(values))
    estimates.sort()
    ci = [round(estimates[int(.025 * bootstrap_runs)], 6),
          round(estimates[min(bootstrap_runs - 1, int(.975 * bootstrap_runs))], 6)]
    result["measurements"]["difference_block_bootstrap_95pct_ci"] = ci
    if not immutable_evidence:
        result["reason"] = "PREDICTION_PROVENANCE_NOT_INDEPENDENTLY_VERIFIED"
    elif ci[0] <= 0:
        result["reason"] = "NO_CLEAR_OUT_OF_SAMPLE_GAIN_OVER_MARKET"
    else:
        result["reason"] = "FURTHER_FORWARD_VALIDATION_AND_CLV_REQUIRED"
    return result


def publish(site, csv_path):
    site = Path(site)
    if not Path(csv_path).is_file():
        result = {
            "status": "HOLD",
            "reason": "NO_VERIFIED_POINT_IN_TIME_PREDICTIONS",
            "n": 0,
            "measurements": None,
            "market_baseline_comparable": False,
            "immutable_forecast_evidence_verified": False,
            "certified_profitable_model": False,
            "production_recommendations": "DISABLED",
        }
    else:
        try:
            result = evaluate(read_rows(csv_path))
        except (ValueError, OSError, TypeError, OverflowError) as exc:
            result = {"status": "HOLD", "reason": "SHADOW_LOG_REJECTED_" + type(exc).__name__,
                      "details": str(exc)[:120], "n": 0, "measurements": None,
                      "production_recommendations": "DISABLED"}
    site.mkdir(parents=True, exist_ok=True)
    (site / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8")
    index = site / "index.html"
    body = index.read_text(encoding="utf-8")
    extra = ('<section id="shadow-validation"><h2>概率與市場基準實證</h2>'
             '<p>目前狀態：<b>HOLD（尚未取得可證實的模型優勢）</b></p>'
             '<p class="small">理由：' + html.escape(result["reason"]) +
             '。必須有賽前時間戳、合法當時賠率、市場概率及已結算賽果，'
             '並完成樣本外比較。只係計算出分數，唔代表真實可盈利。</p>'
             '<p><a href="validation.json">查看驗證證據與樣本量</a></p></section>')
    if 'id="shadow-validation"' not in body:
        body = body.replace('<h2>七大缺口狀態</h2>', extra + '<h2>七大缺口狀態</h2>', 1)
    index.write_text(body, encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--site", default="app/site")
    p.add_argument("--input", default="inputs/shadow_predictions.csv")
    a = p.parse_args()
    print(json.dumps(publish(a.site, a.input), ensure_ascii=False))
