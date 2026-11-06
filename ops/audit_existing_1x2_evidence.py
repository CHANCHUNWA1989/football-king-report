"""Read-only audit of existing forward 1X2 settled evidence. Never approves bets."""
import argparse
import json
import math
from collections import Counter
from datetime import datetime

PRODUCTION_RECOMMENDATIONS = "DISABLED"


def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed


def _vector(values):
    if (not isinstance(values, list) or len(values) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 <= v <= 1 for v in values)
            or abs(sum(values) - 1) > 0.002):
        raise ValueError("invalid probability vector")
    return values


def audit(data):
    if not isinstance(data, dict) or data.get("production_recommendations") != "DISABLED":
        raise ValueError("unsafe archive")
    samples = data.get("samples")
    if not isinstance(samples, list) or len(samples) > 20000:
        raise ValueError("invalid sample collection")
    reasons = Counter()
    leagues = Counter()
    scores = {"model_brier": 0.0, "market_brier": 0.0,
              "model_log_loss": 0.0, "market_log_loss": 0.0}
    valid = 0
    independent = 0
    missing_model_hash = 0
    missing_result_source = 0
    kickoff_dates = []
    seen = set()
    for row in samples:
        try:
            if not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED":
                raise ValueError("unsafe row")
            key = row["key"]
            if not isinstance(key, str) or key in seen:
                raise ValueError("duplicate or invalid key")
            seen.add(key)
            market, forecast, kickoff = (_time(row[k]) for k in
                                         ("market_utc", "forecast_utc", "kickoff_utc"))
            if not market <= forecast < kickoff:
                raise ValueError("invalid chronology")
            y = row["y"]
            if type(y) is not int or y not in (0, 1, 2):
                raise ValueError("invalid outcome")
            p, m = _vector(row["p"]), _vector(row["m"])
            if not isinstance(row.get("league"), str) or not row["league"]:
                raise ValueError("invalid league")
            if not isinstance(row.get("model_artifact_sha256"), str) or len(row.get("model_artifact_sha256", "")) != 64:
                missing_model_hash += 1
            if not isinstance(row.get("fixture_result_source"), str) or not row.get("fixture_result_source"):
                missing_result_source += 1
            kickoff_dates.append(kickoff.date().isoformat())
            if row.get("fixture_result_source_independently_verified") is True:
                independent += 1
            for name, v in (("model", p), ("market", m)):
                scores[name + "_brier"] += sum((v[i] - int(i == y)) ** 2 for i in range(3))
                scores[name + "_log_loss"] -= math.log(max(v[y], 1e-15))
            leagues[row["league"]] += 1
            valid += 1
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            reasons[str(exc)] += 1
    return {
        "status": "HOLD",
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
        "input_rows": len(samples),
        "valid_rows": valid,
        "excluded_rows": len(samples) - valid,
        "exclusion_reasons": dict(reasons),
        "league_counts": dict(sorted(leagues.items())),
        "independently_verified_outcome_rows": independent,
        "missing_model_artifact_hash_rows": missing_model_hash,
        "missing_result_source_rows": missing_result_source,
        "kickoff_date_range": ([min(kickoff_dates), max(kickoff_dates)] if kickoff_dates else None),
        "all_outcomes_independently_verified": bool(valid and independent == valid
            and data.get("results_independently_verified") is True),
        "profitability_verified": False,
        "score_summary_unverified": ({k: v / valid for k, v in scores.items()} if valid else None),
        "warning": "Descriptive 1X2 scores only; no bookmaker prices, Asian EV or certified ROI.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", help="existing evidence/settled.json")
    args = parser.parse_args()
    with open(args.archive, encoding="utf-8") as stream:
        data = json.load(stream)
    print(json.dumps(audit(data), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
