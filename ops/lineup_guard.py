"""Fail-closed, point-in-time lineup evidence quality gate (research only).

This checks *structure* and forecast chronology of separately obtained lineup
data. HTTPS links, metadata or source labels are NOT authentication. It does
not assert that a forecast used a lineup or that lineup data are licensed.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit

SCHEMA = "football-king-lineup-chronology-audit-v1"
MAX_AGE_BEFORE_KICKOFF_SECONDS = 3 * 3600


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("INVALID_TIME")
    return d.astimezone(timezone.utc)


def _names(players):
    if not isinstance(players, list) or len(players) != 11:
        return False
    if any(not isinstance(n, str) or not (1 <= len(n.strip()) <= 120)
           or any(ord(ch) < 32 for ch in n) for n in players):
        return False
    return len({n.casefold().strip() for n in players}) == 11


def audit(forecast):
    """Return no names, no source payload, no odds and never a bet permission."""
    result = {
        "schema": SCHEMA, "status": "MISSING",
        "reason": "NO_LINEUP_EVIDENCE",
        "lineup_usable_before_prediction": False,
        "independent_origin_authenticated": False,
        "official_lineup_authenticated": False,
        "model_lineup_incorporation_verified": False,
        "eligible_for_betting": False,
        "production_recommendations": "DISABLED",
    }
    if not isinstance(forecast, dict):
        return {**result, "status": "HOLD", "reason": "INVALID_FORECAST"}
    if "lineup_evidence" not in forecast:
        return result
    evidence = forecast["lineup_evidence"]
    if not isinstance(evidence, dict):
        return {**result, "status": "HOLD", "reason": "INVALID_LINEUP_RECORD"}
    try:
        fixture = evidence["fixture"]
        if (not isinstance(fixture, dict)
                or fixture.get("league") != forecast["league"]
                or fixture.get("home") != forecast["home"]
                or fixture.get("away") != forecast["away"]):
            raise ValueError("LINEUP_FIXTURE_MISMATCH")
        kickoff = _utc(forecast["kickoff_utc"])
        if _utc(fixture["kickoff_utc"]) != kickoff:
            raise ValueError("LINEUP_KICKOFF_MISMATCH")
        prediction = _utc(forecast["prediction_utc"])
        published = _utc(evidence["published_utc"])
        captured = _utc(evidence["captured_utc"])
        if not published <= captured <= prediction < kickoff:
            raise ValueError("LINEUP_AFTER_FORECAST_OR_INVALID_TIME")
        if (kickoff - published).total_seconds() > MAX_AGE_BEFORE_KICKOFF_SECONDS:
            raise ValueError("LINEUP_TOO_EARLY_TO_ATTEST")
        if not (_names(evidence["home_starters"]) and _names(evidence["away_starters"])):
            raise ValueError("INVALID_STARTING_XI")
        if ({n.casefold().strip() for n in evidence["home_starters"]}
                & {n.casefold().strip() for n in evidence["away_starters"]}):
            raise ValueError("CROSS_TEAM_DUPLICATE_PLAYER")
        url = evidence["source_url"]
        if not isinstance(url, str) or len(url) > 1200:
            raise ValueError("INVALID_SOURCE_URL")
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 443)):
            raise ValueError("INVALID_SOURCE_URL")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        reason = str(exc) if str(exc) in (
            "LINEUP_FIXTURE_MISMATCH", "LINEUP_KICKOFF_MISMATCH",
            "LINEUP_AFTER_FORECAST_OR_INVALID_TIME", "LINEUP_TOO_EARLY_TO_ATTEST",
            "INVALID_STARTING_XI", "CROSS_TEAM_DUPLICATE_PLAYER",
            "INVALID_SOURCE_URL") else "INVALID_LINEUP_RECORD"
        return {**result, "status": "HOLD", "reason": reason}
    return {
        **result, "status": "STRUCTURAL_RESEARCH_ONLY",
        "reason": "PRE_FORECAST_LINEUP_STRUCTURALLY_VALID_BUT_SOURCE_UNATTESTED",
        "lineup_usable_before_prediction": True,
    }
