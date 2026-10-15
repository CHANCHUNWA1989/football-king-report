"""Offline, research-only probability scoring against settled football outcomes.

Input rows require an immutable pre-match prediction timestamp and later
settlement timestamp. No claims of market value, profit or recommendation.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def score(rows):
    if not isinstance(rows, list) or len(rows) > 100000:
        raise ValueError("INVALID_ROWS")
    accepted = []
    rejects = {}
    seen = set()
    for row in rows:
        try:
            if not isinstance(row, dict):
                raise ValueError("INVALID_ROW")
            key = row["event_id"]
            if not isinstance(key, str) or not key.strip() or key in seen:
                raise ValueError("DUPLICATE_OR_MISSING_EVENT")
            seen.add(key)
            forecast = stamp(row["forecast_utc"])
            kickoff = stamp(row["kickoff_utc"])
            settled = stamp(row["settled_utc"])
            if not forecast < kickoff < settled:
                raise ValueError("TIME_LEAKAGE_OR_UNSETTLED")
            outcome = row["result"]
            if outcome not in ("H", "D", "A"):
                raise ValueError("INVALID_RESULT")
            probs = [row["p_home"], row["p_draw"], row["p_away"]]
            if any(type(p) not in (float, int) or not math.isfinite(p)
                   or p < 0 or p > 1 for p in probs):
                raise ValueError("INVALID_PROBABILITIES")
            if abs(sum(probs) - 1) > 0.0001:
                raise ValueError("UNNORMALIZED_PROBABILITIES")
            y = [float(outcome == label) for label in ("H", "D", "A")]
            brier = sum((p - actual) ** 2 for p, actual in zip(probs, y))
            logloss = -math.log(max(probs[("H", "D", "A").index(outcome)], 1e-15))
            correct = ("H", "D", "A")[max(range(3), key=lambda i: probs[i])] == outcome
            accepted.append((brier, logloss, correct))
        except (KeyError, ValueError, TypeError, OverflowError) as exc:
            reason = str(exc) if isinstance(exc, ValueError) else "INVALID_RECORD"
            rejects[reason] = rejects.get(reason, 0) + 1
    n = len(accepted)
    return {
        "schema": "football-king-shadow-1x2-scoring-v1",
        "status": "RESEARCH_ONLY" if n else "HOLD",
        "accepted": n,
        "rejected": len(rows) - n,
        "reject_reasons": dict(sorted(rejects.items())),
        "mean_brier": round(sum(x[0] for x in accepted) / n, 6) if n else None,
        "mean_log_loss": round(sum(x[1] for x in accepted) / n, 6) if n else None,
        "top_probability_accuracy": round(sum(x[2] for x in accepted) / n, 6) if n else None,
        "minimum_sample_for_skill_claim_met": n >= 1000,
        "independent_market_baseline_verified": False,
        "out_of_sample_verified": False,
        "production_recommendations": "DISABLED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", default="market/shadow_1x2_score.json")
    args = p.parse_args()
    result = score(json.loads(Path(args.input).read_text(encoding="utf-8")))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps({"status": result["status"], "accepted": result["accepted"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
