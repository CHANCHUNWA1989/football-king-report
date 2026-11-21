"""Outcome-blind league cohort home-favourite concentration safety sentinel.

Review-only policy: at least 10 distinct valid pre-match forecasts in a
league, strictly more than 80% favour HOME -> quarantine *unmarketed model-
only* research watchlist. Never alter probabilities, score outcomes, claim
a calibrated home-win prior, or block independently validated market research.
This threshold is a conservative warning heuristic, NOT empirically optimal.
"""
import math
from datetime import datetime, timedelta, timezone

SCHEMA = "football-king-home-favourite-concentration-review-v1"
MIN_CASES = 10
MAX_HOME_TOP_SHARE = 0.80
LEAGUES = frozenset(("epl","championship","bundesliga","laliga","seriea","ligue1"))


def _utc(value):
    """Parse real timezone-aware instant; never treat a display string as proof."""
    if type(value) is not str or not value or len(value) > 90:
        raise ValueError("INVALID_SENTINEL_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("INVALID_SENTINEL_TIME")
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("INVALID_SENTINEL_TIME") from None


def assess(predictions, *, now=None, model_capture=None):
    if type(predictions) is not list or len(predictions) > 5000:
        raise ValueError("INVALID_HOME_BIAS_COHORT")
    if (now is None) != (model_capture is None):
        raise ValueError("INVALID_SENTINEL_TIME_SCOPE")
    if now is not None:
        if (type(now) is not datetime or type(model_capture) is not datetime
                or now.tzinfo is None or now.utcoffset() is None
                or model_capture.tzinfo is None or model_capture.utcoffset() is None):
            raise ValueError("INVALID_SENTINEL_TIME_SCOPE")
        now = now.astimezone(timezone.utc)
        model_capture = model_capture.astimezone(timezone.utc)
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
        try:
            prediction = _utc(row["prediction_utc"])
            kickoff = _utc(row["kickoff_utc"])
            if prediction >= kickoff:
                raise ValueError("FORECAST_NOT_BEFORE_KICKOFF")
            # A model-only watchlist is built from one captured research
            # snapshot. Ignore records that its actual candidate filter will
            # reject for source capture mismatch or expired kickoff window.
            if now is not None and (
                abs((prediction - model_capture).total_seconds()) > 120
                or prediction > now + timedelta(minutes=5)
                or not 60 * 60 <= (kickoff - now).total_seconds()
                <= 7 * 24 * 3600
            ):
                raise ValueError("INELIGIBLE_FOR_CURRENT_FALLBACK")
        except (ValueError, KeyError, TypeError, OverflowError):
            bucket["excluded"] += 1
            continue
        p = [row.get(k) for k in ("p_home","p_draw","p_away")]
        if (any(type(x) not in (int,float) or not math.isfinite(x)
                or x < 0 or x > 1 for x in p)
                or abs(sum(p)-1) > 0.002):
            bucket["excluded"] += 1
            continue
        # Tied maximum is not a unique HOME (or AWAY/DRAW) pick.
        # Exclude ambiguous directions rather than silently inflating the
        # denominator or declaring HOME simply because it is first.
        if p.count(max(p)) > 1:
            bucket["excluded"] += 1
            continue
        key = (league, row["event_id"], kickoff.isoformat())
        if key in seen:
            bucket["excluded"] += 1
            continue
        seen.add(key)
        bucket["observations"] += 1
        bucket["home_top"] += int(p[0] > p[1] and p[0] > p[2])
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
