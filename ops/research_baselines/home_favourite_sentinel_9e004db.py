"""Outcome-blind league cohort home-favourite concentration safety sentinel.

Review-only policy: at least 10 distinct valid pre-match forecasts in a
league, strictly more than 80% favour HOME -> quarantine *unmarketed model-
only* research watchlist. Never alter probabilities, score outcomes, claim
a calibrated home-win prior, or block independently validated market research.
This threshold is a conservative warning heuristic, NOT empirically optimal.
"""
import math

SCHEMA = "football-king-home-favourite-concentration-review-v1"
MIN_CASES = 10
MAX_HOME_TOP_SHARE = 0.80
LEAGUES = frozenset(("epl","championship","bundesliga","laliga","seriea","ligue1"))


def assess(predictions):
    if type(predictions) is not list or len(predictions) > 5000:
        raise ValueError("INVALID_HOME_BIAS_COHORT")
    seen = set()
    counts = {league: {"observations": 0, "home_top": 0, "excluded": 0}
              for league in sorted(LEAGUES)}
    for row in predictions:
        if type(row) is not dict:
            continue
        league = row.get("league")
        if type(league) is not str or league not in LEAGUES:
            continue
        bucket = counts[league]
        if (row.get("production_recommendations") != "DISABLED"
                or row.get("status") not in (None, "SCHEDULED")
                or any(row.get(k) is not None for k in
                       ("score_ft","result","historical_outcome"))
                or any(type(row.get(k)) is not str or not row[k] for k in
                       ("event_id","kickoff_utc","prediction_utc"))):
            bucket["excluded"] += 1
            continue
        p = [row.get(k) for k in ("p_home","p_draw","p_away")]
        if (any(type(x) not in (int,float) or not math.isfinite(x)
                or x < 0 or x > 1 for x in p)
                or abs(sum(p)-1) > 0.002):
            bucket["excluded"] += 1
            continue
        key = (league, row["event_id"], row["kickoff_utc"])
        if key in seen:
            bucket["excluded"] += 1
            continue
        seen.add(key)
        bucket["observations"] += 1
        bucket["home_top"] += int(p[0] == max(p))
    result = {}
    for league, bucket in sorted(counts.items()):
        total = bucket["observations"]
        fraction = (bucket["home_top"] / total) if total else None
        review = (total >= MIN_CASES
                  and bucket["home_top"] * 5 > total * 4)
        result[league] = {
            "valid_distinct_pre_match_forecasts": total,
            "home_top_forecasts": bucket["home_top"],
            "excluded_unusable_or_duplicate_rows": bucket["excluded"],
            "home_top_share": round(fraction, 6) if fraction is not None else None,
            "minimum_observations_for_warning": MIN_CASES,
            "review_threshold_strictly_greater_than": MAX_HOME_TOP_SHARE,
            "sufficient_cohort_for_warning": total >= MIN_CASES,
            "home_favourite_concentration_review": bool(review),
            "fallback_model_only_watchlist_allowed": not review,
            "model_probability_adjusted": False,
            "validated_calibration": False,
            "positive_ev_verified": False,
        }
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY",
        "by_league": result,
        "calibration_or_prediction_uplift_proven": False,
        "production_recommendations": "DISABLED",
    }
