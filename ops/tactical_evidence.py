"""Fail-closed tactical evidence assessment for low-block research.

This is NOT a computer-vision classifier. Formations alone never prove a
parked bus. Data must come from separately authenticated match sources.
No provider calls, betting recommendations, or odds are emitted.
"""
from datetime import datetime, timezone

MAX_STATS_AGE_SECONDS = 180


def _clock(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.astimezone(timezone.utc) if result.tzinfo else None


def assess(case, *, now_utc):
    now = _clock(now_utc)
    if now is None:
        raise ValueError("INVALID_NOW_UTC")
    result = {
        "schema": "football-king-tactical-evidence-v1",
        "status": "HOLD",
        "low_block_assessment": "UNKNOWN",
        "reasons": [],
        "verified_starting_xi": False,
        "verified_live_stats": False,
        "formation_alone_sufficient": False,
        "production_recommendations": "DISABLED",
        "betting_permission": False,
    }
    if not isinstance(case, dict):
        result["reasons"].append("INVALID_CASE")
        return result
    fixture = case.get("fixture")
    lineup = case.get("lineup")
    stats = case.get("live_stats")
    if not isinstance(fixture, dict) or not isinstance(fixture.get("event_id"), str) or not fixture["event_id"]:
        result["reasons"].append("FIXTURE_ID_MISSING")
        return result
    event_id = fixture["event_id"]
    if not isinstance(lineup, dict) or lineup.get("event_id") != event_id:
        result["reasons"].append("OFFICIAL_LINEUP_UNVERIFIED")
    elif lineup.get("official_source_authenticated") is not True:
        result["reasons"].append("OFFICIAL_LINEUP_UNVERIFIED")
    elif not all(isinstance(lineup.get(k), list) and len(lineup[k]) == 11 and
                 all(isinstance(p, str) and p.strip() for p in lineup[k]) and
                 len(set(p.strip().casefold() for p in lineup[k])) == 11
                 for k in ("home_starters", "away_starters")):
        result["reasons"].append("INVALID_STARTING_XI")
    else:
        result["verified_starting_xi"] = True
    if not isinstance(stats, dict) or stats.get("event_id") != event_id or stats.get("independently_verified") is not True:
        result["reasons"].append("LIVE_STATS_UNVERIFIED")
        return result
    stamp = _clock(stats.get("updated_at_utc"))
    if stamp is None or not 0 <= (now - stamp).total_seconds() <= MAX_STATS_AGE_SECONDS:
        result["reasons"].append("LIVE_STATS_STALE")
        return result
    result["verified_live_stats"] = True
    # These are explicitly provider-derived defensive-position indicators.
    # Shots, possession and five-at-the-back formations are NOT sufficient.
    indicators = stats.get("defensive_position_indicators")
    if not isinstance(indicators, dict):
        result["reasons"].append("DEFENSIVE_POSITION_EVIDENCE_MISSING")
        return result
    if indicators.get("source_authenticated") is not True:
        result["reasons"].append("DEFENSIVE_POSITION_SOURCE_UNVERIFIED")
        return result
    sample = indicators.get("observed_minutes")
    deep = indicators.get("deep_block_minutes")
    if (type(sample) is not int or type(deep) is not int
            or sample < 15 or deep < 0 or deep > sample):
        result["reasons"].append("INSUFFICIENT_DEFENSIVE_POSITION_SAMPLE")
        return result
    ratio = deep / sample
    result["status"] = "RESEARCH_ONLY"
    result["deep_block_time_share"] = round(ratio, 3)
    result["low_block_assessment"] = ("SUSTAINED_LOW_BLOCK_EVIDENCE" if ratio >= 0.65
                                       else "MIXED_OR_HIGHER_BLOCK_EVIDENCE")
    result["reasons"].append("RESEARCH_HEURISTIC_NOT_INDEPENDENTLY_CALIBRATED")
    return result
