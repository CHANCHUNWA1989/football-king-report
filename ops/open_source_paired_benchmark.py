"""Independent, offline 1X2 evaluation inspired by open research practices.

No external project code is copied. No betting advice or promotion permission.
Input: sealed evidence/settled.json (unverified observations remain unverified).
"""
import argparse
import json
import math
import random
from datetime import datetime
from pathlib import Path

LABELS = ("home", "draw", "away")


def _score(row, field):
    p = row.get(field)
    y = row.get("y")
    if type(y) is not int or y not in range(3):
        return None
    if not isinstance(p, list) or len(p) != 3:
        return None
    if any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 or v > 1 for v in p):
        return None
    if abs(sum(p) - 1) > 1e-3:
        return None
    return (float(max(range(3), key=lambda i: p[i]) == y),
            -math.log(max(float(p[y]), 1e-15)),
            sum((float(v) - float(i == y)) ** 2 for i, v in enumerate(p)))


def compare(rows, *, bootstrap_reps=2000, seed=17):
    """Paired bootstrap resamples fixtures, never individual selections."""
    if type(bootstrap_reps) is not int or not 1 <= bootstrap_reps <= 100000:
        raise ValueError("INVALID_BOOTSTRAP_REPS")
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    pairs = []
    seen = set()
    verified = 0
    invalid_chronology = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("key")
        if not isinstance(key, str) or key in seen:
            raise ValueError("DUPLICATE_OR_INVALID_FIXTURE_KEY")
        seen.add(key)
        a, m = _score(row, "p"), _score(row, "m")
        if a is None or m is None:
            continue
        verified += row.get("fixture_result_source_independently_verified") is True
        try:
            kickoff, forecast, market = (
                datetime.fromisoformat(row[k].replace("Z", "+00:00"))
                for k in ("kickoff_utc", "forecast_utc", "market_utc")
            )
            if any(t.tzinfo is None or t.utcoffset() is None for t in (kickoff, forecast, market)):
                raise ValueError("timezone required")
            if not (forecast < kickoff and market < kickoff):
                raise ValueError("post-kickoff evidence")
        except (KeyError, TypeError, ValueError, AttributeError):
            invalid_chronology += 1
        pairs.append((a, m))
    n = len(pairs)
    out = {
        "schema": "football-king-paired-bootstrap-research-v1",
        "status": "RESEARCH_ONLY" if n and verified == n and invalid_chronology == 0 else "HOLD",
        "sample_count": n,
        "independently_verified_result_count": verified,
        "invalid_or_missing_chronology_count": invalid_chronology,
        "data_quality_pass": bool(n and verified == n and invalid_chronology == 0),
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "betting_roi_estimable": False,
        "metrics": {},
        "paired_difference_95pct_bootstrap_ci": {},
    }
    if not n:
        return out
    names = ("accuracy", "log_loss", "brier")
    for j, name in enumerate(names):
        ma = sum(p[0][j] for p in pairs) / n
        mm = sum(p[1][j] for p in pairs) / n
        out["metrics"][name] = {"model_A": round(ma, 6), "market": round(mm, 6),
                                "model_minus_market": round(ma - mm, 6)}
    rng = random.Random(seed)
    for j, name in enumerate(names):
        diffs = [a[j] - m[j] for a, m in pairs]
        samples = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n
                         for _ in range(bootstrap_reps))
        low = samples[int(0.025 * (bootstrap_reps - 1))]
        high = samples[int(0.975 * (bootstrap_reps - 1))]
        out["paired_difference_95pct_bootstrap_ci"][name] = [round(low, 6), round(high, 6)]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("evidence/settled.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise ValueError("INVALID_EVIDENCE")
    result = compare(data["samples"])
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
