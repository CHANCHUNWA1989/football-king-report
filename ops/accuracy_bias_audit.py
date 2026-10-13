"""Research-only paired 1X2 accuracy, class bias and market benchmark audit.

No prediction modification, no betting activation, no model promotion.
Input is the already-settled and point-in-time validated rows produced by
ops.model_evidence.read_rows (not a live or independently verified feed).
"""
import argparse
import json
import math
from collections import Counter, defaultdict

OUTCOMES = ("home", "draw", "away")


def audit(rows):
    if not isinstance(rows, list):
        raise ValueError("ROWS_MUST_BE_LIST")
    counts = {"model": Counter(), "market": Counter(), "actual": Counter()}
    hits = {"model": Counter(), "market": Counter()}
    by_league = defaultdict(lambda: {"n": 0, "model_hits": 0, "market_hits": 0})
    n = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("BAD_ROW")
        for key in ("p", "m"):
            p = row.get(key)
            if (not isinstance(p, (list, tuple)) or len(p) != 3
                    or not all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in p)
                    or abs(sum(p) - 1) > 0.002):
                raise ValueError("BAD_PROBABILITIES")
        y = row.get("y")
        if type(y) is not int or y not in (0, 1, 2):
            raise ValueError("BAD_OUTCOME")
        league = row.get("league", "unknown")
        if not isinstance(league, str) or not league.strip():
            league = "unknown"
        n += 1
        actual = OUTCOMES[y]
        counts["actual"][actual] += 1
        group = by_league[league]
        group["n"] += 1
        for key, model in (("model", "p"), ("market", "m")):
            pick = OUTCOMES[max(range(3), key=lambda i: row[model][i])]
            counts[key][pick] += 1
            if pick == actual:
                hits[key][actual] += 1
                group[key + "_hits"] += 1
    def class_counts(counter):
        return {k: counter[k] for k in OUTCOMES}
    result = {
        "schema": "football-king-accuracy-bias-audit-v1",
        "status": "RESEARCH_ONLY" if n else "HOLD",
        "n": n,
        "model_correct": sum(hits["model"].values()),
        "market_correct": sum(hits["market"].values()),
        "model_accuracy": sum(hits["model"].values()) / n if n else None,
        "market_accuracy": sum(hits["market"].values()) / n if n else None,
        "predicted_counts": {k: class_counts(counts[k]) for k in ("model", "market")},
        "actual_counts": class_counts(counts["actual"]),
        "correct_by_outcome": {k: class_counts(hits[k]) for k in ("model", "market")},
        "model_home_pick_share": counts["model"]["home"] / n if n else None,
        "actual_home_win_share": counts["actual"]["home"] / n if n else None,
        "home_bias_review_flag": (n >= 20 and
            counts["model"]["home"] / n - counts["actual"]["home"] / n >= 0.20),
        "by_league": dict(by_league),
        "outcomes_independently_verified": False,
        "sample_sufficient_for_promotion": False,
        "executable_odds_verified": False,
        "qualifies_for_betting": False,
        "production_recommendations": "DISABLED",
        "warning": "描述性事後審計；未獨立核實賽果，不能證明未來命中率或投注價值。",
    }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Sealed research CSV with model/market/outcome")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    from model_evidence import read_rows
    rows = read_rows(args.input)
    report = audit(rows)
    with open(args.output, "w", encoding="utf-8") as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
