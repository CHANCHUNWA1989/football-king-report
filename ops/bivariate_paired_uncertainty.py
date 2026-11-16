"""Deterministic paired calendar-date cluster bootstrap, REUSED holdout ONLY.

A 2025->2026 date split is genuine score-only historical evaluation but the
186-match 2026 cohort has already been inspected. Intervals are descriptive,
not independent confirmatory evidence, wagering confidence, or EV.
"""
from collections import defaultdict
from datetime import date
import math
import random

from .asian_handicap_research import TYPES
from .real_2026_three_market_oos import _score

SCHEMA = "football-king-bivariate-paired-uncertainty-v1"
RNG_SEED = 20261116
BOOTSTRAP_DRAWS = 2000
COMPARISONS = (
    ("bivariate_poisson", "dixon_coles"),
    ("bivariate_poisson_time_decay", "bivariate_poisson"),
)
MARKET_CLASSES = {
    "1X2": ("HOME", "DRAW", "AWAY"),
    "TOTAL_OVER_2.75": TYPES,
    "AH_HOME_-0.25": TYPES,
}


def _percentile(sorted_values, q):
    position = (len(sorted_values) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    return (sorted_values[low] * (high - position) +
            sorted_values[high] * (position - low)) if low != high else sorted_values[low]


def evaluate(dates, observed, forecasts):
    """Estimate paired loss delta (first minus second); negative means better.

    Cluster by source calendar day to keep contemporaneous international games
    together. No record selection, market-line search, promotion, or live inputs.
    """
    if (type(dates) is not list or not dates
            or any(type(x) is not str or len(x) != 10 for x in dates)
            or type(observed) is not dict or type(forecasts) is not dict):
        raise ValueError("INVALID_UNCERTAINTY_INPUT")
    try:
        if any(date.fromisoformat(x).isoformat() != x for x in dates):
            raise ValueError("INVALID_CALENDAR_DAY")
    except (ValueError, TypeError):
        raise ValueError("INVALID_CALENDAR_DAY") from None
    days = sorted(set(dates))
    group = defaultdict(list)
    for i, day in enumerate(dates):
        group[day].append(i)
    n = len(dates)
    if set(observed) != set(MARKET_CLASSES):
        raise ValueError("MISSING_PAIRED_MARKET")
    for market in MARKET_CLASSES:
        if type(observed[market]) is not list or len(observed[market]) != n:
            raise ValueError("UNPAIRED_OBSERVED_MARKETS")
        if any(outcome not in MARKET_CLASSES[market] for outcome in observed[market]):
            raise ValueError("INVALID_OBSERVED_MARKET_CLASS")
    for candidate, baseline in COMPARISONS:
        for name in (candidate, baseline):
            if name not in forecasts or type(forecasts[name]) is not dict:
                raise ValueError("MISSING_MODEL_PAIRED_COHORT")
            for market in MARKET_CLASSES:
                rows = forecasts[name].get(market)
                if type(rows) is not list or len(rows) != n:
                    raise ValueError("INCOMPLETE_MODEL_PAIRED_COHORT")

    result = {}
    for comparison_id, (candidate, baseline) in enumerate(COMPARISONS):
        market_output = {}
        for market_id, (market, classes) in enumerate(MARKET_CLASSES.items()):
            losses = {name: [
                _score(forecasts[name][market][i], observed[market][i], classes)
                for i in range(n)]
                for name in (candidate, baseline)}
            values = {}
            for metric_id, label in enumerate(("brier", "logloss")):
                differences = [
                    losses[candidate][i][metric_id] -
                    losses[baseline][i][metric_id]
                    for i in range(n)
                ]
                observed_delta = sum(differences) / n
                # Resample *calendar dates*, not independent same-day fixtures.
                # One common fixture-index pair under both models in every draw.
                day_sums = [sum(differences[i] for i in group[day])
                            for day in days]
                day_counts = [len(group[day]) for day in days]
                if len(days) < 5:
                    interval = None
                    interpretation = "INSUFFICIENT_DISTINCT_SOURCE_DATES"
                else:
                    rng = random.Random(RNG_SEED + 100 * comparison_id +
                                        10 * market_id + metric_id)
                    draw_means = []
                    for _ in range(BOOTSTRAP_DRAWS):
                        choices = [rng.randrange(len(days)) for _ in days]
                        total = sum(day_sums[x] for x in choices)
                        count = sum(day_counts[x] for x in choices)
                        draw_means.append(total / count)
                    draw_means.sort()
                    interval = [round(_percentile(draw_means, 0.025), 6),
                                round(_percentile(draw_means, 0.975), 6)]
                    interpretation = "REUSED_HOLDOUT_EXPLORATORY_ONLY"
                values[label] = {
                    "mean_candidate_minus_baseline": round(observed_delta, 6),
                    "day_cluster_bootstrap_95pct_interval": interval,
                    "contains_zero": (None if interval is None else
                                      interval[0] <= 0 <= interval[1]),
                    "status": interpretation,
                }
            market_output[market] = values
        result[f"{candidate}_minus_{baseline}"] = market_output
    return {
        "schema": SCHEMA, "method": "paired calendar-date cluster percentile bootstrap",
        "source_calendar_day_clusters": len(days),
        "paired_fixture_count": n,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "fixed_rng_seed": RNG_SEED,
        "candidate_minus_baseline_negative_is_better": True,
        "independent_confirmatory_evidence": False,
        "reused_holdout_for_model_choice": True,
        "market_odds_or_ev_verified": False,
        "model_promoted": False,
        "comparisons": result,
    }
