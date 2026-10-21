"""Fail-closed, provider-neutral daily football research report builder.

Inputs are supplied by a separate, trusted acquisition process. This module
does not fetch fixtures or odds, estimate win probabilities, verify execution,
or enable betting. A report item is NOT a verified positive-EV recommendation.
"""
from datetime import datetime, timezone
from math import isfinite
from ops.free_odds_intake import normalize_quote

PRODUCTION_RECOMMENDATIONS = "HOLD"

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIME") from None
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return t.astimezone(timezone.utc)

def build_daily_research_report(rows, *, generated_utc, max_quote_age_minutes=60):
    """Return reviewable research cards, never executable betting picks.

    Each row requires fixture_id, kickoff_utc, home_team, away_team and quote.
    quote must match fixture_id. Optional model_probability is informational
    only; it is NOT calibrated and must never be called verified EV.
    """
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    if type(max_quote_age_minutes) not in (int, float) or not isfinite(max_quote_age_minutes) or max_quote_age_minutes <= 0:
        raise ValueError("INVALID_MAX_AGE")
    now = _utc(generated_utc)
    cards = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ROW")
        fixture = row.get("fixture_id")
        if not isinstance(fixture, str) or not fixture.strip():
            raise ValueError("MISSING_FIXTURE_ID")
        if fixture in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(fixture)
        for field in ("home_team", "away_team"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("MISSING_" + field.upper())
        kickoff = _utc(row.get("kickoff_utc"))
        if kickoff <= now:
            status, reason, quote = "NO_RECOMMENDATION", "MATCH_STARTED_OR_FINISHED", None
        elif not isinstance(row.get("quote"), dict):
            status, reason, quote = "NO_RECOMMENDATION", "MISSING_QUOTE", None
        else:
            quote = normalize_quote(row["quote"], captured_utc=generated_utc)
            if quote["fixture_id"] != fixture:
                raise ValueError("QUOTE_FIXTURE_MISMATCH")
            quote_time = _utc(quote["quote_utc"])
            if (now - quote_time).total_seconds() > max_quote_age_minutes * 60:
                status, reason = "NO_RECOMMENDATION", "STALE_QUOTE"
            elif quote_time >= kickoff:
                status, reason = "NO_RECOMMENDATION", "QUOTE_NOT_PREMATCH"
            else:
                status, reason = "RESEARCH_ONLY", "UNVERIFIED_MARKET_RESEARCH"
        probability = row.get("model_probability")
        if probability is not None:
            if type(probability) not in (int, float) or not isfinite(probability) or not 0 < probability < 1:
                raise ValueError("INVALID_MODEL_PROBABILITY")
        cards.append({
            "fixture_id": fixture, "home_team": row["home_team"],
            "away_team": row["away_team"], "kickoff_utc": kickoff.isoformat(),
            "status": status, "reason": reason, "quote": quote,
            "model_probability_uncalibrated": probability,
            "ev_status": "UNVERIFIED_NOT_CALIBRATED",
            "positive_ev_verified": False,
            "betting_recommendation": "HOLD",
        })
    return {
        "generated_utc": now.isoformat(),
        "sample_count": len(cards),
        "research_only_count": sum(c["status"] == "RESEARCH_ONLY" for c in cards),
        "cards": cards,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
        "automated_betting": "DISABLED",
        "positive_ev_verified": False,
    }
