"""Explicit provider-field normalization, without network calls or license assumptions.

Only an already-authorized caller may assert source rights. Missing data fails
closed in downstream live_feed_admission; this adapter never grants rights.
"""
from live_feed_admission import admit_live_feed


def normalize_and_admit(raw, *, now=None):
    if not isinstance(raw, dict):
        return {"status": "HOLD", "reason": "INVALID_PROVIDER_PAYLOAD",
                "production_recommendations": "DISABLED", "observations": []}
    match, market = raw.get("match"), raw.get("market")
    if not isinstance(match, dict) or not isinstance(market, dict):
        return {"status": "HOLD", "reason": "MISSING_PROVIDER_FEED",
                "production_recommendations": "DISABLED", "observations": []}
    score = {
        "source_event_id": match.get("event_id"),
        "source_authorized": match.get("licensed") is True,
        "status": match.get("state"),
        "minute": match.get("elapsed_minute"),
        "home_goals": match.get("home_score"),
        "away_goals": match.get("away_score"),
        "source_last_update_utc": match.get("updated_at"),
    }
    quote = {
        "source_event_id": market.get("event_id"),
        "bookmaker": market.get("bookmaker"),
        "market": market.get("market_key"),
        "selection": market.get("outcome"),
        "market_last_update_utc": market.get("updated_at"),
        "decimal_odds": market.get("price"),
        "source_authorized": market.get("licensed") is True,
        "is_live": market.get("in_play") is True,
        "probabilities_are_no_vig_consensus": market.get("consensus") is True,
    }
    return admit_live_feed({"score": score, "quote": quote}, now=now)
