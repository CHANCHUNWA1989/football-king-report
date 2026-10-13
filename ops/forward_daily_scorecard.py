"""Daily transparent forward 1X2 scoreboard from already sealed, settled observations.

Descriptive only: public-source final scores have not been independently authenticated.
Never synthesize missing market quotes or post-hoc challenger forecasts.
"""
import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from evidence_merge import validate
from market_shrinkage import blend

WEIGHTS = (0.0, 0.5, 0.75, 1.0)
TARGET = 1000


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
    daily = defaultdict(list)
    for row in rows:
        stamp = datetime.fromisoformat(row["kickoff_utc"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("NAIVE_KICKOFF")
        day = stamp.astimezone(timezone.utc).date().isoformat()
        daily[day].append(row)
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
        "daily_utc": [
            {"date": day, "observations": len(daily[day]),
             "comparisons": compare(daily[day])}
            for day in sorted(daily)
        ],
        "same_cases_for_all_four_weights": True,
        "retrospective_reconstruction_of_blends": True,
        "independent_forward_challenger_registration_proven": False,
        "market_quotes_are_executable": False,
        "results_independently_verified": False,
        "statistical_superiority_proven": False,
        "production_recommendations": "DISABLED",
        "warning": "Observational scores on recorded point-in-time model/market pairs; outcomes are not independently verified. Blend comparisons are retrospective, not separately sealed forward challengers. Accuracy does not establish betting profitability.",
    }


def publish(source, site):
    p = Path(source)
    if p.is_file():
        evidence = json.loads(p.read_text(encoding="utf-8"))
    else:
        evidence = {"schema": "football-king-forward-research-1",
                    "checked_utc": datetime.now(timezone.utc).isoformat(),
                    "samples": [], "n": 0,
                    "results_independently_verified": False,
                    "profitability_verified": False,
                    "production_recommendations": "DISABLED"}
    result = build(evidence)
    dest = Path(site)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "forward_daily_scorecard.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
