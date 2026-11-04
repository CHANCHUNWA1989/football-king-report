"""Reconcile The Odds API sports catalogue without making any network requests.

Catalogue presence is discovery evidence only, not entitlement or live odds.
"""
from ops.european_coverage import audit

CANDIDATE_KEYS = {
    "uefa-champions-league": "soccer_uefa_champs_league",
    "uefa-europa-league": "soccer_uefa_europa_league",
    "uefa-conference-league": "soccer_uefa_europa_conference_league",
    "premier-league": "soccer_epl",
    "la-liga": "soccer_spain_la_liga",
    "serie-a": "soccer_italy_serie_a",
    "bundesliga": "soccer_germany_bundesliga",
    "ligue-1": "soccer_france_ligue_one",
}


def reconcile(sports):
    """Accept vendor /v4/sports/ array; never expose secrets or bookmaker odds."""
    scope = audit()["competitions"]
    if not isinstance(sports, list) or len(sports) > 10000:
        raise ValueError("INVALID_SPORTS_CATALOGUE")
    available = {}
    duplicates = set()
    seen = set()
    for item in sports:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str) or len(key) > 128:
            continue
        if key in seen:
            duplicates.add(key)
            available[key] = None
        else:
            seen.add(key)
            available[key] = item.get("active") if type(item.get("active")) is bool else None
    results = []
    for slug in scope:
        key = CANDIDATE_KEYS[slug]
        active = None if key in duplicates else available.get(key)
        results.append({
            "competition": slug,
            "candidate_sport_key": key,
            "catalogue_status": "ACTIVE_CANDIDATE" if active is True else (
                "INACTIVE_CANDIDATE" if active is False else "NOT_VERIFIED"),
            "season_entitled": False,
            "live_odds_verified": False,
            "production_recommendations": "DISABLED",
        })
    return {"status": "HOLD", "provider": "the-odds-api.com/v4",
            "catalogue_only": True, "results": results,
            "production_recommendations": "DISABLED"}
