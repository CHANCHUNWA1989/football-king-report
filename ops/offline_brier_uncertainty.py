"""Paired heldout Brier uncertainty via deterministic event-level bootstrap.

Exploratory IID event resampling only. Correlated matches require grouped/time-block
bootstrap before inference. This does not establish betting EV.
"""
import math
import random
from offline_temporal_split import split_historical_forecasts


def paired_brier_uncertainty(rows, *, test_fraction=0.2, embargo_hours=24,
                             repetitions=2000, seed=0):
    hold = {"status": "HOLD", "reason": "INSUFFICIENT_PAIRED_UNCERTAINTY_DATA",
            "production_recommendations": "DISABLED"}
    if (type(repetitions) is not int or not 200 <= repetitions <= 10000
            or type(seed) is not int or not 0 <= seed <= 2**32 - 1):
        return hold
    split = split_historical_forecasts(
        rows, test_fraction=test_fraction, embargo_hours=embargo_hours)
    if split["status"] != "RESEARCH_ONLY":
        return hold
    ids = set(split["test_event_ids"])
    deltas = []
    for row in rows:
        if row["event_id"] not in ids:
            continue
        p, b, y = row.get("probability"), row.get("baseline_probability"), row.get("outcome")
        if (type(p) not in (int, float) or type(b) not in (int, float)
                or not math.isfinite(p) or not math.isfinite(b)
                or not 0 <= p <= 1 or not 0 <= b <= 1
                or type(y) is not int or y not in (0, 1)):
            return hold
        deltas.append((p - y)**2 - (b - y)**2)
    if len(deltas) < 30:
        return hold
    rng = random.Random(seed)
    n = len(deltas)
    draws = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(repetitions))
    low = draws[int(0.025 * repetitions)]
    high = draws[min(int(0.975 * repetitions), repetitions - 1)]
    return {
        "status": "RESEARCH_ONLY", "reason": "EXPLORATORY_PAIRED_BRIER_BOOTSTRAP",
        "test_count": n, "mean_brier_delta": round(sum(deltas) / n, 6),
        "ci95_low": round(low, 6), "ci95_high": round(high, 6),
        "interval_excludes_zero": low > 0 or high < 0,
        "bootstrap_method": "iid_event_percentile_exploratory",
        "source_authenticity_verified": False, "model_validated": False,
        "positive_ev_verified": False, "production_recommendations": "DISABLED",
    }
