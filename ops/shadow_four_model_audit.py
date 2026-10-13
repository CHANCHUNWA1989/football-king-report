"""Fail-closed, paired four-model 1X2 scoring for sealed pre-match records.

Input JSON: {"records":[{"fixture_id":"...", "kickoff_utc":"...", "sealed_at_utc":"...",
"result_verified_at_utc":"...", "result":"home|draw|away",
"result_verified":true, "model":[...], "market":[...]}]}.
Only genuinely verified final scores and pre-kickoff forecasts are accepted.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

LABELS = {"home": 0, "draw": 1, "away": 2}

def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def vector(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("expected three probabilities")
    if not all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 1 for x in value):
        raise ValueError("invalid probabilities")
    if abs(sum(value) - 1) > 0.002:
        raise ValueError("probabilities must sum to one")
    return [float(x) / sum(value) for x in value]

def evaluate(records):
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    unique = {}
    rejected = {}
    for row in records:
        try:
            if not isinstance(row, dict) or row.get("result_verified") is not True:
                raise ValueError("unverified result")
            key = row["fixture_id"]
            if not isinstance(key, str) or not key.strip():
                raise ValueError("missing fixture id")
            sealed, kickoff, verified = (timestamp(row[k]) for k in
                ("sealed_at_utc", "kickoff_utc", "result_verified_at_utc"))
            if not sealed < kickoff < verified:
                raise ValueError("invalid chronology")
            if row["result"] not in LABELS:
                raise ValueError("invalid result")
            original, market = vector(row["model"]), vector(row["market"])
            signature = (sealed.isoformat(), row["result"], tuple(original), tuple(market))
            if key in unique:
                if unique[key][0] != signature:
                    unique[key] = None  # quarantine conflicting records
                continue
            unique[key] = (signature, original, market, LABELS[row["result"]])
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            reason = str(exc)
            rejected[reason] = rejected.get(reason, 0) + 1
    metrics = {name: {"hits": 0, "brier_sum": 0.0, "log_loss_sum": 0.0}
               for name in ("original", "market", "market_50", "market_75")}
    for entry in unique.values():
        if entry is None:
            rejected["conflicting duplicate"] = rejected.get("conflicting duplicate", 0) + 1
            continue
        _, original, market, outcome = entry
        variants = {"original": original, "market": market,
                    "market_50": [0.5*a+0.5*b for a,b in zip(original,market)],
                    "market_75": [0.25*a+0.75*b for a,b in zip(original,market)]}
        for name, probabilities in variants.items():
            m = metrics[name]
            m["hits"] += int(probabilities.index(max(probabilities)) == outcome)
            m["brier_sum"] += sum((p-int(i == outcome))**2 for i,p in enumerate(probabilities))
            m["log_loss_sum"] += -math.log(max(probabilities[outcome], 1e-15))
    count = sum(v is not None for v in unique.values())
    summary = {name: {"sample_size": count,
                      "accuracy": m["hits"]/count if count else None,
                      "brier": m["brier_sum"]/count if count else None,
                      "log_loss": m["log_loss_sum"]/count if count else None}
               for name,m in metrics.items()}
    return {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
            "valid_fixtures": count, "target": 1000, "remaining": max(0,1000-count),
            "rejected": rejected, "models": summary}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = evaluate(payload["records"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

if __name__ == "__main__":
    main()
