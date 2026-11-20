"""Research-only live-feed admission layer.

The pre-match recommender must never consume this in-play feed as if it were
sealed pre-match evidence. No bookmaker credentials, network calls or bets.
"""
from live_snapshot_gate import assess_snapshot


def admit_live_feed(payload, *, now=None):
    if not isinstance(payload, dict):
        return {"status": "HOLD", "reason": "INVALID_PAYLOAD",
                "production_recommendations": "DISABLED", "observations": []}
    score, quote = payload.get("score"), payload.get("quote")
    decision = assess_snapshot(score, quote, now=now)
    output = {"status": decision["status"], "reason": decision["reason"],
              "production_recommendations": "DISABLED", "observations": []}
    if decision["status"] != "RESEARCH_ONLY":
        return output
    output["observations"] = [{
        "source_event_id": score["source_event_id"],
        "minute": score["minute"],
        "home_goals": score["home_goals"],
        "away_goals": score["away_goals"],
        "score_updated_utc": score["source_last_update_utc"],
        "market": quote["market"],
        "selection": quote["selection"],
        "bookmaker": quote["bookmaker"],
        "market_updated_utc": quote["market_last_update_utc"],
        "decimal_odds": quote["decimal_odds"],
        "research_only": True,
        "validated_positive_ev": False,
    }]
    return output
