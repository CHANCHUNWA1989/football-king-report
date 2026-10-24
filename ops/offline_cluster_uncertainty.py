"""Exploratory calendar-week cluster bootstrap for heldout Brier differences.

Cluster by UTC kickoff ISO week to retain within-week dependence.
This is not a validated causal or betting-EV inference procedure.
"""
import math
import random
from datetime import datetime, timezone
from offline_temporal_split import split_historical_forecasts


def weekly_cluster_brier_uncertainty(rows, *, test_fraction=0.2,
                                     embargo_hours=24, repetitions=2000, seed=0):
    hold = {"status": "HOLD", "reason": "INSUFFICIENT_WEEKLY_CLUSTERS",
            "production_recommendations": "DISABLED"}
    if (type(repetitions) is not int or not 200 <= repetitions <= 10000
            or type(seed) is not int or not 0 <= seed <= 2**32 - 1):
        return hold
    split = split_historical_forecasts(rows, test_fraction=test_fraction,
                                       embargo_hours=embargo_hours)
    if split["status"] != "RESEARCH_ONLY":
        return hold
    ids = set(split["test_event_ids"])
    clusters = {}
    for row in rows:
        if row["event_id"] not in ids:
            continue
        p, b, y = row.get("probability"), row.get("baseline_probability"), row.get("outcome")
        if (type(p) not in (float, int) or type(b) not in (float, int)
                or not math.isfinite(p) or not math.isfinite(b)
                or not 0 <= p <= 1 or not 0 <= b <= 1
                or type(y) is not int or y not in (0, 1)):
            return hold
        try:
            kickoff = datetime.fromisoformat(row["kickoff_at_utc"].replace("Z", "+00:00"))
            week = kickoff.astimezone(timezone.utc).isocalendar()[:2]
        except (ValueError, AttributeError, TypeError):
            return hold
        clusters.setdefault(week, []).append((p-y)**2 - (b-y)**2)
    if len(clusters) < 8:
        return hold
    groups = list(clusters.values())
    total = sum(map(len, groups))
    observed = sum(sum(group) for group in groups) / total
    rng = random.Random(seed)
    means = []
    for _ in range(repetitions):
        chosen = [groups[rng.randrange(len(groups))] for _ in groups]
        means.append(sum(sum(g) for g in chosen) / sum(len(g) for g in chosen))
    means.sort()
    low = means[int(0.025 * repetitions)]
    high = means[min(int(0.975 * repetitions), repetitions - 1)]
    return {
        "status": "RESEARCH_ONLY", "reason": "EXPLORATORY_WEEKLY_CLUSTER_BOOTSTRAP",
        "test_count": total, "cluster_count": len(groups),
        "mean_brier_delta": round(observed, 6),
        "ci95_low": round(low, 6), "ci95_high": round(high, 6),
        "interval_excludes_zero": low > 0 or high < 0,
        "bootstrap_method": "utc_iso_week_cluster_percentile_exploratory",
        "model_validated": False, "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }
