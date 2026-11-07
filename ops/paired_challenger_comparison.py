"""Offline same-fixture model comparison; never promotes models or emits betting tips."""
import argparse
import json
import math
from datetime import datetime


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return dt


def _probabilities(values):
    if not isinstance(values, list) or len(values) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 or v > 1 for v in values):
        raise ValueError("INVALID_PROBABILITIES")
    if abs(sum(values) - 1) > 1e-6:
        raise ValueError("INVALID_PROBABILITIES")
    return values


def evaluate(rows):
    """Rows contain sealed forecasts from both models and a market baseline.

    Every row must have key, kickoff_utc, as_of_utc, y, model_a, challenger,
    market, independently_verified, and sealed_before_kickoff.
    Missing or invalid rows fail the entire cohort closed; no cherry-picking.
    """
    if not isinstance(rows, list) or not rows:
        return {"status": "HOLD", "reason": "EMPTY_COHORT", "production_recommendations": "DISABLED"}
    seen = set()
    scores = {k: {"accuracy": 0., "log_loss": 0., "brier": 0.}
              for k in ("model_a", "challenger", "market")}
    try:
        for row in rows:
            if not isinstance(row, dict) or set(row) != {
                "key", "kickoff_utc", "as_of_utc", "y", "model_a", "challenger",
                "market", "independently_verified", "sealed_before_kickoff"
            }:
                raise ValueError("INVALID_ROW_SCHEMA")
            key = row["key"]
            if not isinstance(key, str) or not key or key in seen:
                raise ValueError("DUPLICATE_OR_INVALID_KEY")
            seen.add(key)
            if row["independently_verified"] is not True or row["sealed_before_kickoff"] is not True:
                raise ValueError("UNVERIFIED_OR_UNSEALED")
            if not _time(row["as_of_utc"]) < _time(row["kickoff_utc"]):
                raise ValueError("LOOKAHEAD")
            y = row["y"]
            if type(y) is not int or y not in range(3):
                raise ValueError("INVALID_OUTCOME")
            for name, totals in scores.items():
                p = _probabilities(row[name])
                totals["accuracy"] += int(max(range(3), key=lambda i: p[i]) == y)
                totals["log_loss"] += -math.log(max(p[y], 1e-15))
                totals["brier"] += sum((v - int(i == y)) ** 2 for i, v in enumerate(p))
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return {"status": "HOLD", "reason": str(exc),
                "production_recommendations": "DISABLED"}
    n = len(rows)
    return {"status": "RESEARCH_ONLY", "sample_count": n,
            "metrics": {name: {metric: round(value / n, 6) for metric, value in totals.items()}
                        for name, totals in scores.items()},
            "positive_ev_verified": False, "production_recommendations": "DISABLED",
            "model_promoted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict) or payload.get("schema") != "football-king-challenger-paired-v1":
        raise ValueError("INVALID_CONTRACT")
    print(json.dumps(evaluate(payload.get("rows")), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
